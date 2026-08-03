"""Unit tests for the Universal Template Framework runtime engine (Phase 0).

Pure-function tests for evaluate_visibility / score_response /
validate_mandatory / grade_for_score -- no DB. get_effective_template's
inheritance is covered by integration tests once a router exists (Phase 1).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.template_engine import (
    evaluate_visibility,
    grade_bands_for_module,
    grade_for_score,
    score_response,
    validate_mandatory,
)


# ---------------------------------------------------------------------------
# helpers: lightweight stand-ins for TemplateDefinition/Section/Question.
# score_response/validate_mandatory only touch attributes, so SimpleNamespace
# keeps these tests DB-free.
# ---------------------------------------------------------------------------

def q(key, qtype="text", scoring=None, visibility=None, mandatory=False, visible=True):
    return SimpleNamespace(
        question_key=key,
        question_type=qtype,
        scoring_rule=scoring,
        visibility_rule=visibility,
        mandatory_flag=mandatory,
        visible_flag=visible,
    )


def section(questions, visibility=None):
    return SimpleNamespace(visibility_rule=visibility, questions=questions)


def template(sections):
    return SimpleNamespace(sections=sections)


# ---------------------------------------------------------------------------
# evaluate_visibility
# ---------------------------------------------------------------------------

class TestEvaluateVisibility:
    def test_null_rule_always_visible(self):
        assert evaluate_visibility(None, {}) is True
        assert evaluate_visibility({}, {}) is True

    def test_parent_yes(self):
        """Spec Section 8: show question if parent question = Yes."""
        rule = {"field": "diversity_required", "op": "eq", "value": "yes"}
        assert evaluate_visibility(rule, {"diversity_required": "yes"}) is True
        assert evaluate_visibility(rule, {"diversity_required": "no"}) is False
        assert evaluate_visibility(rule, {}) is False  # unanswered -> hidden

    def test_neq_true_when_unanswered(self):
        rule = {"field": "country", "op": "neq", "value": "US"}
        assert evaluate_visibility(rule, {}) is True
        assert evaluate_visibility(rule, {"country": "US"}) is False
        assert evaluate_visibility(rule, {"country": "DE"}) is True

    def test_numeric_threshold_string_answer(self):
        """The _coerce_numeric lesson: JSON answers arrive as strings."""
        rule = {"field": "annual_spend", "op": "gte", "value": 50000}
        assert evaluate_visibility(rule, {"annual_spend": "50000"}) is True
        assert evaluate_visibility(rule, {"annual_spend": "49999.99"}) is False
        assert evaluate_visibility(rule, {"annual_spend": 60000}) is True

    def test_incomparable_fails_closed(self):
        rule = {"field": "annual_spend", "op": "gt", "value": 100}
        assert evaluate_visibility(rule, {"annual_spend": "not a number"}) is False

    def test_in_operator_scalar_and_multiselect(self):
        rule = {"field": "region", "op": "in", "value": ["US", "CA"]}
        assert evaluate_visibility(rule, {"region": "US"}) is True
        assert evaluate_visibility(rule, {"region": "MX"}) is False
        # multiselect answer: any overlap counts
        assert evaluate_visibility(rule, {"region": ["MX", "CA"]}) is True
        assert evaluate_visibility(rule, {"region": ["MX", "BR"]}) is False

    def test_nested_all_any(self):
        rule = {
            "all": [
                {"field": "supplier_type", "op": "eq", "value": "manufacturer"},
                {
                    "any": [
                        {"field": "country", "op": "eq", "value": "US"},
                        {"field": "risk_level", "op": "eq", "value": "high"},
                    ]
                },
            ]
        }
        assert evaluate_visibility(rule, {"supplier_type": "manufacturer", "country": "US"}) is True
        assert evaluate_visibility(rule, {"supplier_type": "manufacturer", "risk_level": "high"}) is True
        assert evaluate_visibility(rule, {"supplier_type": "manufacturer", "country": "DE"}) is False
        assert evaluate_visibility(rule, {"supplier_type": "distributor", "country": "US"}) is False

    def test_empty_all_any(self):
        assert evaluate_visibility({"all": []}, {}) is True   # vacuous truth
        assert evaluate_visibility({"any": []}, {}) is False  # nothing can match

    def test_unknown_operator_fails_closed(self):
        assert evaluate_visibility({"field": "x", "op": "regex", "value": ".*"}, {"x": "y"}) is False


# ---------------------------------------------------------------------------
# grading + scoring
# ---------------------------------------------------------------------------

class TestGrading:
    @pytest.mark.parametrize(
        "score,grade",
        [
            (Decimal("100"), "A"),
            (Decimal("90"), "A"),
            (Decimal("89.99"), "B"),
            (Decimal("80"), "B"),
            (Decimal("79.99"), "C"),
            (Decimal("70"), "C"),
            (Decimal("69.99"), "D"),
            (Decimal("60"), "D"),
            (Decimal("59.99"), "F"),
            (Decimal("0"), "F"),
        ],
    )
    def test_spec_section_7_bands(self, score, grade):
        assert grade_for_score(score) == grade


class TestFSRegistrationGrading:
    """Supplier Type/Registration FS Section 9's 4-band scale (no F), scoped
    to supplier_registration_* modules only -- every other module (including
    the default/no-module case above) keeps the original 5-band scale."""

    def test_module_resolution(self):
        assert grade_bands_for_module("supplier_registration_core")[0] == (Decimal("90"), "A")
        assert grade_bands_for_module("slp") == grade_bands_for_module(None)

    @pytest.mark.parametrize(
        "score,grade",
        [
            (Decimal("100"), "A"),
            (Decimal("90"), "A"),
            (Decimal("89.99"), "B"),
            (Decimal("75"), "B"),
            (Decimal("74.99"), "C"),
            (Decimal("50"), "C"),
            (Decimal("49.99"), "D"),
            (Decimal("0"), "D"),
        ],
    )
    def test_fs_section_9_boundaries(self, score, grade):
        assert grade_for_score(score, module="supplier_registration_core") == grade

    def test_score_response_uses_module_bands_automatically(self):
        """score_response reads template.module -- callers never pass bands
        explicitly for the common case."""
        tpl = template([section([q("iso9001", "yes_no", scoring={"weight": 100, "map": {"yes": 10, "no": 0}})])])
        tpl.module = "supplier_registration_compliance"
        score, grade = score_response(tpl, {"iso9001": "no"})
        assert score == Decimal("0.00")
        assert grade == "D"  # not "F" -- FS bands have no F


class TestScoreResponse:
    def test_simple_map_scoring(self):
        tpl = template([
            section([
                q("iso9001", "yes_no", scoring={"weight": 50, "map": {"yes": 10, "no": 0}}),
                q("financials", "dropdown", scoring={"weight": 50, "map": {"audited": 10, "unaudited": 5, "none": 0}}),
            ])
        ])
        score, grade = score_response(tpl, {"iso9001": "yes", "financials": "unaudited"})
        # 50*100 + 50*50 over weight 100 -> 75.00
        assert score == Decimal("75.00")
        assert grade == "C"

    def test_numeric_threshold_scoring(self):
        tpl = template([
            section([q("employees", "numeric", scoring={"weight": 100, "threshold": 50, "above": 10, "below": 2})])
        ])
        score, _ = score_response(tpl, {"employees": "75"})
        assert score == Decimal("100.00")
        score, grade = score_response(tpl, {"employees": 10})
        assert score == Decimal("20.00")
        assert grade == "F"

    def test_unanswered_scored_question_counts_as_zero(self):
        tpl = template([
            section([
                q("a", scoring={"weight": 50, "map": {"yes": 10}}),
                q("b", scoring={"weight": 50, "map": {"yes": 10}}),
            ])
        ])
        score, grade = score_response(tpl, {"a": "yes"})
        assert score == Decimal("50.00")
        assert grade == "F"

    def test_hidden_question_excluded_and_weights_renormalized(self):
        """A conditional question hidden for this respondent must not drag
        the score down -- weights renormalize over visible questions."""
        tpl = template([
            section([
                q("base", scoring={"weight": 50, "map": {"yes": 10, "no": 0}}),
                q(
                    "diversity_cert",
                    scoring={"weight": 50, "map": {"yes": 10, "no": 0}},
                    visibility={"field": "diversity_required", "op": "eq", "value": "yes"},
                ),
            ])
        ])
        # Hidden: only `base` participates -> perfect score.
        score, grade = score_response(tpl, {"base": "yes", "diversity_required": "no"})
        assert score == Decimal("100.00")
        assert grade == "A"
        # Visible and unanswered: zero-scored at full weight.
        score, _ = score_response(tpl, {"base": "yes", "diversity_required": "yes"})
        assert score == Decimal("50.00")

    def test_hidden_section_excluded(self):
        tpl = template([
            section([q("a", scoring={"weight": 10, "map": {"yes": 10}})]),
            section(
                [q("b", scoring={"weight": 90, "map": {"yes": 10}})],
                visibility={"field": "supplier_type", "op": "eq", "value": "manufacturer"},
            ),
        ])
        score, _ = score_response(tpl, {"a": "yes", "supplier_type": "distributor"})
        assert score == Decimal("100.00")

    def test_boolean_yes_no_answer(self):
        tpl = template([section([q("flag", "yes_no", scoring={"weight": 100, "map": {"yes": 10, "no": 0}})])])
        score, _ = score_response(tpl, {"flag": True})
        assert score == Decimal("100.00")
        score, _ = score_response(tpl, {"flag": False})
        assert score == Decimal("0.00")

    def test_present_rule_free_text(self):
        tpl = template([
            section([
                q("justification", "textarea", scoring={"weight": 50, "present": 10}),
                q("check", "yes_no", scoring={"weight": 50, "map": {"yes": 10, "no": 0}}),
            ])
        ])
        score, _ = score_response(tpl, {"justification": "we need this", "check": "yes"})
        assert score == Decimal("100.00")
        score, _ = score_response(tpl, {"justification": "", "check": "yes"})
        assert score == Decimal("50.00")
        score, _ = score_response(tpl, {"check": "yes"})
        assert score == Decimal("50.00")

    def test_nothing_scoreable_returns_none(self):
        tpl = template([section([q("comment")])])
        assert score_response(tpl, {"comment": "hello"}) == (None, None)


# ---------------------------------------------------------------------------
# validate_mandatory
# ---------------------------------------------------------------------------

class TestValidateMandatory:
    def test_hidden_mandatory_not_missing(self):
        tpl = template([
            section([
                q("diversity_required", "yes_no", mandatory=True),
                q(
                    "diversity_cert",
                    "file_upload",
                    mandatory=True,
                    visibility={"field": "diversity_required", "op": "eq", "value": "yes"},
                ),
            ])
        ])
        assert validate_mandatory(tpl, {"diversity_required": "no"}) == []
        assert validate_mandatory(tpl, {"diversity_required": "yes"}) == ["diversity_cert"]
        assert validate_mandatory(tpl, {"diversity_required": "yes", "diversity_cert": "cert.pdf"}) == []

    def test_empty_string_and_list_count_as_missing(self):
        tpl = template([section([q("name", mandatory=True), q("tags", "multiselect", mandatory=True)])])
        assert validate_mandatory(tpl, {"name": "", "tags": []}) == ["name", "tags"]

    def test_unimplemented_type_raises(self):
        tpl = template([section([q("grid", "table_grid")])])
        with pytest.raises(ValueError, match="unimplemented type"):
            validate_mandatory(tpl, {})
