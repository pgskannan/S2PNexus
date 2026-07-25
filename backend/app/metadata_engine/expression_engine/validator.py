"""Expression validator for metadata expressions."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.metadata_engine.expression_engine.ast import (
    BinaryOpNode,
    ExpressionNode,
    FunctionNode,
    IdentifierNode,
    LiteralNode,
    ObjectNode,
    UnaryOpNode,
)


@dataclass
class ExpressionValidationResult:
    is_valid: bool
    errors: list[str]
    dependencies: set[str]
    has_cycle: bool = False


class ExpressionValidator:
    """Validate expression syntax, dependencies, and cycles."""

    SUPPORTED_FUNCTIONS = {
        "IF",
        "AND",
        "OR",
        "NOT",
        "CASE",
        "SUM",
        "AVG",
        "COUNT",
        "MAX",
        "MIN",
        "LOOKUP",
        "TODAY",
        "NOW",
        "DATEADD",
        "DATEDIFF",
    }

    def validate(self, node: ExpressionNode) -> ExpressionValidationResult:
        errors: list[str] = []
        has_cycle = self._detect_cycle(node)
        if has_cycle:
            errors.append("Cycle detected")
            return ExpressionValidationResult(
                is_valid=False,
                errors=errors,
                dependencies=set(),
                has_cycle=True,
            )

        self._validate_node(node, errors, set())
        dependencies = node.dependencies()
        return ExpressionValidationResult(
            is_valid=not errors,
            errors=errors,
            dependencies=dependencies,
            has_cycle=False,
        )

    def _validate_node(self, node: ExpressionNode, errors: list[str], seen: set[int]) -> None:
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)

        if isinstance(node, FunctionNode):
            if node.name not in self.SUPPORTED_FUNCTIONS:
                errors.append(f"Unsupported function: {node.name}")
            for arg in node.args:
                self._validate_node(arg, errors, seen)
            return
        if isinstance(node, ObjectNode):
            for value in node.properties.values():
                self._validate_node(value, errors, seen)
            return
        if isinstance(node, BinaryOpNode):
            if node.operator not in {"AND", "OR", "==", "!=", "<", ">", "<=", ">=", "+", "-", "*", "/"}:
                errors.append(f"Unsupported binary operator: {node.operator}")
            self._validate_node(node.left, errors, seen)
            self._validate_node(node.right, errors, seen)
            return
        if isinstance(node, UnaryOpNode):
            if node.operator not in {"NOT", "NEG"}:
                errors.append(f"Unsupported unary operator: {node.operator}")
            self._validate_node(node.operand, errors, seen)
            return
        if isinstance(node, IdentifierNode):
            if not node.name:
                errors.append("Empty identifier")
            return
        if isinstance(node, LiteralNode):
            return
        errors.append(f"Unknown expression node type: {type(node).__name__}")

    def _detect_cycle(self, node: ExpressionNode, visited: set[int] | None = None, stack: set[int] | None = None) -> bool:
        if visited is None:
            visited = set()
        if stack is None:
            stack = set()

        node_id = id(node)
        if node_id in stack:
            return True
        if node_id in visited:
            return False

        stack.add(node_id)
        visited.add(node_id)

        child_nodes = []
        if isinstance(node, FunctionNode):
            child_nodes.extend(node.args)
        elif isinstance(node, BinaryOpNode):
            child_nodes.extend([node.left, node.right])
        elif isinstance(node, UnaryOpNode):
            child_nodes.append(node.operand)
        elif isinstance(node, ObjectNode):
            child_nodes.extend(node.properties.values())

        for child in child_nodes:
            if self._detect_cycle(child, visited, stack):
                return True

        stack.remove(node_id)
        return False
