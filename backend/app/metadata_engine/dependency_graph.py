"""Metadata dependency graph and impact analysis primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DependencyNode:
    node_id: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DependencyEdge:
    source_id: str
    target_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DependencyGraph:
    """Simple directed graph of metadata dependencies."""

    def __init__(self) -> None:
        self.nodes: dict[str, DependencyNode] = {}
        self.edges: list[DependencyEdge] = []

    def add_node(self, node: DependencyNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: DependencyEdge) -> None:
        self.edges.append(edge)

    def get_outgoing(self, node_id: str) -> list[DependencyEdge]:
        return [edge for edge in self.edges if edge.source_id == node_id]

    def get_incoming(self, node_id: str) -> list[DependencyEdge]:
        return [edge for edge in self.edges if edge.target_id == node_id]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DependencyGraph":
        graph = cls()
        for node_payload in payload.get("nodes", []):
            graph.add_node(
                DependencyNode(
                    node_id=node_payload["node_id"],
                    name=node_payload.get("name", node_payload["node_id"]),
                    metadata=node_payload.get("metadata", {}),
                )
            )
        for edge_payload in payload.get("edges", []):
            graph.add_edge(
                DependencyEdge(
                    source_id=edge_payload["source_id"],
                    target_id=edge_payload["target_id"],
                    metadata=edge_payload.get("metadata", {}),
                )
            )
        return graph


class ImpactAnalysisService:
    """Provides dependency discovery, cycle detection, and impact analysis."""

    def discover_dependencies(self, graph: DependencyGraph, node_id: str) -> list[DependencyNode]:
        visited: set[str] = set()
        ordered: list[DependencyNode] = []

        def walk(current_id: str) -> None:
            if current_id in visited:
                return
            visited.add(current_id)
            if current_id != node_id:
                node = graph.nodes.get(current_id)
                if node is not None:
                    ordered.append(node)
            for edge in graph.get_outgoing(current_id):
                target = graph.nodes.get(edge.target_id)
                if target is not None and target.node_id not in visited:
                    walk(target.node_id)

        walk(node_id)
        return ordered

    def detect_circular_dependencies(self, graph: DependencyGraph) -> list[list[str]]:
        cycles: list[list[str]] = []
        visited: set[str] = set()
        stack: list[str] = []
        stack_set: set[str] = set()

        def visit(node_id: str) -> None:
            visited.add(node_id)
            stack.append(node_id)
            stack_set.add(node_id)
            for edge in graph.get_outgoing(node_id):
                target_id = edge.target_id
                if target_id in stack_set:
                    idx = stack.index(target_id)
                    cycles.append(stack[idx:] + [target_id])
                    continue
                if target_id not in visited:
                    visit(target_id)
            stack.pop()
            stack_set.remove(node_id)

        for node_id in graph.nodes:
            if node_id not in visited:
                visit(node_id)
        return cycles

    def analyze_impact(self, graph: DependencyGraph, node_id: str) -> dict[str, Any]:
        affected_nodes = [node.node_id for node in self.discover_dependencies(graph, node_id)]
        return {
            "affected_nodes": affected_nodes,
            "has_circular_dependency": bool(self.detect_circular_dependencies(graph)),
        }

    def validate_safe_delete(self, graph: DependencyGraph, node_id: str) -> dict[str, Any]:
        blocking_dependents = [edge.target_id for edge in graph.get_outgoing(node_id)]
        return {
            "is_safe": not blocking_dependents,
            "blocking_dependents": blocking_dependents,
        }
