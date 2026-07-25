"""Unit tests for the metadata expression engine."""

from __future__ import annotations

import pytest
from datetime import date, datetime

from app.metadata_engine.expression_engine.ast import BinaryOpNode, LiteralNode
from app.metadata_engine.expression_engine.engine import ExpressionEngine
from app.metadata_engine.expression_engine.parser import ParseError
from app.metadata_engine.expression_engine.validator import ExpressionValidator


@pytest.fixture
def engine() -> ExpressionEngine:
    return ExpressionEngine()


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("IF(1 == 1, 10, 20)", 10),
        ("AND(1 == 1, 2 == 2)", True),
        ("OR(1 == 2, 2 == 2)", True),
        ("NOT(1 == 2)", True),
        ("CASE(1 == 2, 10, 2 == 2, 20, 30)", 20),
        ("SUM(1, 2, 3)", 6),
        ("AVG(2, 4, 6)", 4),
        ("COUNT(1, 2, 3)", 3),
        ("MAX(1, 5, 2)", 5),
        ("MIN(1, 5, 2)", 1),
    ],
)
def test_function_evaluation(engine: ExpressionEngine, expression: str, expected: object) -> None:
    compiled, validation = engine.parse_validate_compile(expression)
    assert validation.is_valid
    result = engine.evaluate(compiled, {})
    assert result == expected


def test_date_functions(engine: ExpressionEngine) -> None:
    compiled_today, validation_today = engine.parse_validate_compile("TODAY()")
    assert validation_today.is_valid
    assert isinstance(engine.evaluate(compiled_today, {}), date)

    compiled_now, validation_now = engine.parse_validate_compile("NOW()")
    assert validation_now.is_valid
    assert isinstance(engine.evaluate(compiled_now, {}), datetime)

    base = datetime(2026, 1, 1, 0, 0)
    compiled_dateadd, validation_dateadd = engine.parse_validate_compile("DATEADD(NOW(), 'days', 1)")
    assert validation_dateadd.is_valid
    result = engine.evaluate(compiled_dateadd, {"NOW()": base})
    assert isinstance(result, datetime)


def test_expression_parsing_and_dependencies(engine: ExpressionEngine) -> None:
    expression = "Supplier.Risk + ComplianceRisk"
    parsed = engine.parse(expression)
    validation = engine.validate(parsed)
    assert validation.is_valid
    assert validation.dependencies == {"Supplier.Risk", "ComplianceRisk"}


def test_cycle_detection(engine: ExpressionEngine) -> None:
    validator = ExpressionValidator()
    literal = LiteralNode(1)
    cyclic = BinaryOpNode("+", literal, literal)
    object.__setattr__(cyclic, "right", cyclic)

    result = validator.validate(cyclic)
    assert result.has_cycle
    assert "Cycle detected" in result.errors


def test_lookup_function(engine: ExpressionEngine) -> None:
    compiled, validation = engine.parse_validate_compile("LOOKUP('key', {'key': 42})")
    assert validation.is_valid
    assert engine.evaluate(compiled, {}) == 42


def test_parse_error_raises() -> None:
    engine = ExpressionEngine()
    with pytest.raises(ParseError):
        engine.parse("IF(1 == 1, 10")
