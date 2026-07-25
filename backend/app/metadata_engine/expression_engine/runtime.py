"""Runtime evaluator for compiled metadata expressions."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.metadata_engine.expression_engine.compiler import CompiledExpression


@dataclass(frozen=True)
class EvaluationContext:
    values: dict[str, Any]


class ExpressionRuntime:
    """Execute compiled expressions with provided context."""

    def evaluate(self, compiled: CompiledExpression, context: EvaluationContext) -> Any:
        return compiled.evaluate(context.values)
