"""Universal Template Framework runtime engine (spec Sections 4, 7, 8).

Three pure-ish entry points:

- evaluate_visibility(rule, answers): condition-tree evaluation for
  section/question visibility_rule JSON.
- score_response(template, answers): weighted 0-100 composite + A-F grade
  per spec Section 7.
- get_effective_template(db, module, tenant_id): spec Section 4 inheritance
  (tenant-published template wins over global-published; "local" mode is a
  reserved value with no resolution logic in this batch).

The condition grammar here is the single source of truth. The frontend's
DynamicTemplateForm mirrors evaluate_visibility exactly -- if you change the
grammar, change both, and change the docstring shape in models/template.py.

Numeric comparisons deliberately reuse the lesson from
crud/workflow.py._coerce_numeric: answers arrive through JSON, so numbers are
frequently strings ("50000", str(Decimal(...))). Comparing str vs int raises
TypeError, and silently swallowing that to False is exactly the bug
_evaluate_condition had until 2026-08-01. Coerce both sides for ordering
operators; leave eq/neq/in alone (legitimately used on non-numeric fields).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import (
    IMPLEMENTED_QUESTION_TYPES,
    TemplateDefinition,
    TemplateQuestion,
)

GRADE_BANDS = (  # spec Section 7, exact bands
    (Decimal("90"), "A"),
    (Decimal("80"), "B"),
    (Decimal("70"), "C"),
    (Decimal("60"), "D"),
)

_ORDERING_OPS = {"gt", "gte", "lt", "lte"}


def _coerce_numeric(value: Any) -> Any:
    """Same contract as crud.workflow._coerce_numeric (see that docstring)."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return value
    return value


def evaluate_visibility(rule: Optional[dict], answers: dict[str, Any]) -> bool:
    """Evaluate a visibility_rule condition tree against submitted answers.

    Grammar (models/template.py docstring):
      {"field": key, "op": "eq|neq|gt|gte|lt|lte|in", "value": ...}
      {"all": [rule, ...]}   -- every child must pass
      {"any": [rule, ...]}   -- at least one child must pass

    NULL/empty rule means always visible. A missing answer fails ordering and
    eq/in checks (you can't be > a threshold you haven't answered) but passes
    neq -- "field != X" is naturally true when unanswered.
    """
    if not rule:
        return True

    if "all" in rule:
        children = rule["all"] or []
        return all(evaluate_visibility(child, answers) for child in children)
    if "any" in rule:
        children = rule["any"] or []
        return any(evaluate_visibility(child, answers) for child in children)

    field = rule.get("field")
    op = rule.get("op", "eq")
    expected = rule.get("value")
    actual = answers.get(field) if field is not None else None

    if op == "neq":
        return actual != expected
    if actual is None:
        return False
    if op == "eq":
        return actual == expected
    if op == "in":
        if isinstance(actual, (list, tuple, set)):
            # multiselect answer vs expected list: any overlap
            expected_items = expected if isinstance(expected, (list, tuple, set)) else [expected]
            return any(item in expected_items for item in actual)
        return actual in (expected if isinstance(expected, (list, tuple, set)) else [expected])
    if op in _ORDERING_OPS:
        left = _coerce_numeric(actual)
        right = _coerce_numeric(expected)
        try:
            if op == "gt":
                return left > right
            if op == "gte":
                return left >= right
            if op == "lt":
                return left < right
            return left <= right
        except TypeError:
            # Incomparable after best-effort coercion (e.g. text vs number).
            # Fail closed but LOUD in the rule's semantics: the question stays
            # hidden, and the mismatch is a template-authoring bug -- do not
            # extend coercion here to paper over it.
            return False
    # Unknown operator: fail closed rather than guessing.
    return False


def _score_question(question: TemplateQuestion, answer: Any) -> Optional[tuple[Decimal, Decimal]]:
    """Return (weight, score_0_10) for one question, or None if unscored.

    scoring_rule shapes (models/template.py docstring):
      choice/yes_no: {"weight": W, "map": {"<answer>": score}}
      numeric:       {"weight": W, "threshold": T, "above": s, "below": s}
      free text:     {"weight": W, "present": s}  -- any non-empty answer
                     scores s, empty/missing scores 0 (completeness scoring)
    Unanswered scored questions score 0 with full weight -- a blank answer to
    a weighted question is a real signal, not a skip.
    """
    rule = question.scoring_rule
    if not rule:
        return None
    weight = _coerce_numeric(rule.get("weight"))
    if not isinstance(weight, (int, float, Decimal)) or weight <= 0:
        return None
    weight = Decimal(str(weight))

    if "present" in rule:
        answered = answer is not None and answer != "" and answer != []
        score = rule["present"] if answered else 0
        return weight, Decimal(str(score))

    if answer is None:
        return weight, Decimal("0")

    if "map" in rule:
        mapped = rule["map"].get(str(answer))
        if mapped is None and isinstance(answer, bool):
            # yes_no answers may arrive as booleans; map keys are authored
            # as "yes"/"no" or "true"/"false" -- try both spellings.
            mapped = rule["map"].get("yes" if answer else "no")
            if mapped is None:
                mapped = rule["map"].get("true" if answer else "false")
        score = _coerce_numeric(mapped)
        if not isinstance(score, (int, float, Decimal)):
            score = 0
        return weight, Decimal(str(score))

    if "threshold" in rule:
        value = _coerce_numeric(answer)
        threshold = _coerce_numeric(rule["threshold"])
        try:
            above = value >= threshold
        except TypeError:
            return weight, Decimal("0")
        score = rule.get("above", 10) if above else rule.get("below", 0)
        return weight, Decimal(str(score))

    return None


def grade_for_score(score: Decimal) -> str:
    """Map a 0-100 score to A-F per spec Section 7's exact bands."""
    for floor, grade in GRADE_BANDS:
        if score >= floor:
            return grade
    return "F"


def score_response(template: TemplateDefinition, answers: dict[str, Any]) -> tuple[Optional[Decimal], Optional[str]]:
    """Weighted composite score (0-100) + grade for a full submission.

    Only questions that are (a) scored and (b) currently visible given the
    answers count -- a hidden conditional question must not drag the score
    down for respondents it doesn't apply to. Weights are normalized over the
    participating questions, so scores are comparable across respondents who
    saw different subsets. Returns (None, None) if nothing scoreable.
    """
    total_weight = Decimal("0")
    weighted_sum = Decimal("0")
    for section in template.sections:
        if not evaluate_visibility(section.visibility_rule, answers):
            continue
        for question in section.questions:
            if not question.visible_flag:
                continue
            if not evaluate_visibility(question.visibility_rule, answers):
                continue
            scored = _score_question(question, answers.get(question.question_key))
            if scored is None:
                continue
            weight, score_0_10 = scored
            total_weight += weight
            weighted_sum += weight * score_0_10 * 10  # 0-10 -> 0-100 scale

    if total_weight == 0:
        return None, None
    composite = (weighted_sum / total_weight).quantize(Decimal("0.01"))
    return composite, grade_for_score(composite)


def validate_mandatory(template: TemplateDefinition, answers: dict[str, Any]) -> list[str]:
    """Return question_keys of visible, mandatory, unanswered questions.

    Visibility-aware on purpose: a mandatory question hidden by its
    visibility rule is not missing (spec Section 8 -- conditional questions
    are only required when shown). Also rejects answers to questions whose
    type is declared but unimplemented (reserved QUESTION_TYPES tail), so
    an authored-but-unsupported template fails loudly at submit time.
    """
    missing: list[str] = []
    for section in template.sections:
        if not evaluate_visibility(section.visibility_rule, answers):
            continue
        for question in section.questions:
            if not question.visible_flag:
                continue
            if not evaluate_visibility(question.visibility_rule, answers):
                continue
            if question.question_type not in IMPLEMENTED_QUESTION_TYPES:
                raise ValueError(
                    f"Question {question.question_key!r} has unimplemented type "
                    f"{question.question_type!r} (reserved in this batch)"
                )
            answer = answers.get(question.question_key)
            if question.mandatory_flag and (answer is None or answer == "" or answer == []):
                missing.append(question.question_key)
    return missing


async def get_effective_template(
    db: AsyncSession,
    module: str,
    tenant_id: Optional[UUID] = None,
) -> Optional[TemplateDefinition]:
    """Spec Section 4 inheritance: tenant-published beats global-published.

    Within a scope, the highest version wins. Returns None when nothing is
    published for the module (callers fall back to legacy fixed-column
    behavior -- same zero-regression contract as the workflow integrations).
    """
    if tenant_id is not None:
        result = await db.execute(
            select(TemplateDefinition)
            .where(
                TemplateDefinition.module == module,
                TemplateDefinition.status == "published",
                TemplateDefinition.tenant_id == tenant_id,
            )
            .order_by(TemplateDefinition.version.desc())
            .limit(1)
        )
        tenant_template = result.scalar_one_or_none()
        if tenant_template is not None:
            return tenant_template

    result = await db.execute(
        select(TemplateDefinition)
        .where(
            TemplateDefinition.module == module,
            TemplateDefinition.status == "published",
            TemplateDefinition.tenant_id.is_(None),
        )
        .order_by(TemplateDefinition.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
