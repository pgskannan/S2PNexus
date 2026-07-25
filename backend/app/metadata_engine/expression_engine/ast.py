"""Abstract syntax tree nodes for the metadata expression engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ExpressionNode:
    def dependencies(self) -> set[str]:
        raise NotImplementedError()


@dataclass(frozen=True)
class LiteralNode(ExpressionNode):
    value: Any

    def dependencies(self) -> set[str]:
        return set()


@dataclass(frozen=True)
class IdentifierNode(ExpressionNode):
    name: str

    def dependencies(self) -> set[str]:
        return {self.name}


@dataclass(frozen=True)
class UnaryOpNode(ExpressionNode):
    operator: str
    operand: ExpressionNode

    def dependencies(self) -> set[str]:
        return self.operand.dependencies()


@dataclass(frozen=True)
class BinaryOpNode(ExpressionNode):
    operator: str
    left: ExpressionNode
    right: ExpressionNode

    def dependencies(self) -> set[str]:
        return self.left.dependencies() | self.right.dependencies()


@dataclass(frozen=True)
class FunctionNode(ExpressionNode):
    name: str
    args: tuple[ExpressionNode, ...]

    def dependencies(self) -> set[str]:
        deps = set()
        for arg in self.args:
            deps |= arg.dependencies()
        return deps


@dataclass(frozen=True)
class ObjectNode(ExpressionNode):
    properties: dict[str, ExpressionNode]

    def dependencies(self) -> set[str]:
        deps = set()
        for value in self.properties.values():
            deps |= value.dependencies()
        return deps
