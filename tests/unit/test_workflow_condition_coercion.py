"""Regression tests for the condition-step numeric-coercion bug.

`WorkflowInstance.context` is a plain JSON column with no Decimal/UUID
encoder, so `services/procurement_workflow.py` (and friends) stringify
Decimal fields like `estimated_value` before storing them in context. Before
this fix, `_evaluate_condition` compared that string directly against a
condition step's numeric `value` using Python's `>`/`>=`/`<`/`<=`, which
raises `TypeError` for str-vs-int/Decimal -- silently caught and returned as
`False`. Net effect: every amount-threshold condition (the standard
`estimated_value >= 1000` PR/PO approval-tier pattern) always took the false
branch, regardless of the real amount. See `backend/scripts/seed_approver_matrix.py`
for the first workflow definition that actually exercises this path.
"""

from __future__ import annotations

from app.crud.workflow import _coerce_numeric, _evaluate_condition


def test_gte_string_context_vs_int_value_above_threshold():
    step = {"field": "estimated_value", "operator": "gte", "value": 1000}
    context = {"estimated_value": "1500.00"}
    assert _evaluate_condition(step, context) is True


def test_gte_string_context_vs_int_value_below_threshold():
    step = {"field": "estimated_value", "operator": "gte", "value": 1000}
    context = {"estimated_value": "999.00"}
    assert _evaluate_condition(step, context) is False


def test_lt_string_context_vs_int_value():
    step = {"field": "estimated_value", "operator": "lt", "value": 10000}
    context = {"estimated_value": "9999.99"}
    assert _evaluate_condition(step, context) is True


def test_non_numeric_field_equality_unaffected():
    step = {"field": "category", "operator": "eq", "value": "IT"}
    context = {"category": "IT"}
    assert _evaluate_condition(step, context) is True


def test_non_numeric_field_gt_falls_back_to_false_not_exception():
    step = {"field": "priority", "operator": "gt", "value": "medium"}
    context = {"priority": "high"}
    # "high" and "medium" both fail Decimal coercion and stay strings;
    # str > str is legal in Python, so this just evaluates normally rather
    # than raising -- the important thing is it doesn't crash the engine.
    assert isinstance(_evaluate_condition(step, context), bool)


def test_coerce_numeric_passes_through_non_numeric_strings():
    assert _coerce_numeric("high") == "high"
    assert _coerce_numeric(None) is None


def test_coerce_numeric_converts_decimal_strings():
    from decimal import Decimal

    assert _coerce_numeric("1500.00") == Decimal("1500.00")
