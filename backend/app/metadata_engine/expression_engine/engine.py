"""High-level expression engine integrating parser, validator, compiler, and runtime."""

from __future__ import annotations

from app.metadata_engine.expression_engine.compiler import ExpressionCompiler, CompiledExpression
from app.metadata_engine.expression_engine.parser import ParseError, parse_expression
from app.metadata_engine.expression_engine.runtime import EvaluationContext, ExpressionRuntime
from app.metadata_engine.expression_engine.validator import ExpressionValidationResult, ExpressionValidator


class ExpressionEngine:
    """Reusable metadata expression engine for parsing, validating, compiling, and executing expressions."""

    def __init__(self) -> None:
        self.validator = ExpressionValidator()
        self.compiler = ExpressionCompiler()
        self.runtime = ExpressionRuntime()

    def parse(self, source: str):
        return parse_expression(source)

    def validate(self, node) -> ExpressionValidationResult:
        return self.validator.validate(node)

    def compile(self, node) -> CompiledExpression:
        return self.compiler.compile(node)

    def evaluate(self, compiled: CompiledExpression, context: dict[str, object]) -> object:
        return self.runtime.evaluate(compiled, EvaluationContext(values=context))

    def parse_validate_compile(self, source: str) -> tuple[CompiledExpression, ExpressionValidationResult]:
        node = self.parse(source)
        validation = self.validate(node)
        compiled = self.compile(node)
        return compiled, validation
