"""Expression compiler for metadata expression ASTs."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from app.metadata_engine.expression_engine.ast import (
    BinaryOpNode,
    ExpressionNode,
    FunctionNode,
    IdentifierNode,
    LiteralNode,
    ObjectNode,
    UnaryOpNode,
)


@dataclass(frozen=True)
class CompiledExpression:
    evaluate: Callable[[dict[str, object]], object]


class ExpressionCompiler:
    """Compile metadata expressions to fast evaluator functions."""

    def compile(self, node: ExpressionNode) -> CompiledExpression:
        def evaluator(context: dict[str, object]) -> object:
            return self._eval(node, context)

        return CompiledExpression(evaluate=evaluator)

    def _eval(self, node: ExpressionNode, context: dict[str, object]) -> object:
        if isinstance(node, LiteralNode):
            return node.value
        if isinstance(node, IdentifierNode):
            return context.get(node.name)
        if isinstance(node, UnaryOpNode):
            operand = self._eval(node.operand, context)
            if node.operator == "NOT":
                return not bool(operand)
            if node.operator == "NEG":
                return -operand
            raise ValueError(f"Unsupported unary operator: {node.operator}")
        if isinstance(node, BinaryOpNode):
            left = self._eval(node.left, context)
            right = self._eval(node.right, context)
            return self._apply_binary(node.operator, left, right)
        if isinstance(node, FunctionNode):
            args = tuple(self._eval(arg, context) for arg in node.args)
            return self._apply_function(node.name, args, context)
        if isinstance(node, ObjectNode):
            return {key: self._eval(value, context) for key, value in node.properties.items()}
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def _apply_binary(self, operator: str, left: object, right: object) -> object:
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            return left / right
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == "<":
            return left < right
        if operator == ">":
            return left > right
        if operator == "<=":
            return left <= right
        if operator == ">=":
            return left >= right
        if operator == "AND":
            return bool(left) and bool(right)
        if operator == "OR":
            return bool(left) or bool(right)
        raise ValueError(f"Unsupported binary operator: {operator}")

    def _apply_function(self, name: str, args: tuple[object, ...], context: dict[str, object]) -> object:
        name = name.upper()
        if name == "IF":
            condition, true_val, false_val = args
            return true_val if bool(condition) else false_val
        if name == "NOT":
            return not bool(args[0])
        if name == "CASE":
            if len(args) < 3 or len(args) % 2 == 0:
                raise ValueError("CASE requires an odd number of arguments: pairs and a default value")
            for i in range(0, len(args) - 1, 2):
                if bool(args[i]):
                    return args[i + 1]
            return args[-1]
        if name == "SUM":
            return sum(args)
        if name == "AVG":
            return sum(args) / len(args) if args else 0
        if name == "COUNT":
            return len(args)
        if name == "MAX":
            return max(args)
        if name == "MIN":
            return min(args)
        if name == "AND":
            return bool(args[0]) and bool(args[1])
        if name == "OR":
            return bool(args[0]) or bool(args[1])
        if name == "LOOKUP":
            key, mapping = args
            return mapping.get(key)
        if name == "TODAY":
            from datetime import date

            return date.today()
        if name == "NOW":
            from datetime import datetime

            return datetime.now()
        if name == "DATEADD":
            from datetime import timedelta

            value, unit, amount = args
            if unit.lower() == "days":
                return value + timedelta(days=int(amount))
            if unit.lower() == "hours":
                return value + timedelta(hours=int(amount))
            if unit.lower() == "minutes":
                return value + timedelta(minutes=int(amount))
            raise ValueError(f"Unsupported DATEADD unit: {unit}")
        if name == "DATEDIFF":
            value1, value2, unit = args
            diff = value1 - value2
            if unit.lower() == "days":
                return diff.days
            if unit.lower() == "hours":
                return diff.total_seconds() / 3600
            if unit.lower() == "minutes":
                return diff.total_seconds() / 60
            raise ValueError(f"Unsupported DATEDIFF unit: {unit}")
        raise ValueError(f"Unsupported function: {name}")
