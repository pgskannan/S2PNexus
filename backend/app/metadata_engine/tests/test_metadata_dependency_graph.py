"""Tests for metadata dependency graph and impact analysis."""

from __future__ import annotations

from app.metadata_engine.dependency_graph import DependencyEdge, DependencyGraph, DependencyNode, ImpactAnalysisService


def test_detects_circular_dependency() -> None:
    graph = DependencyGraph()
    graph.add_node(DependencyNode(node_id="supplier", name="Supplier"))
    graph.add_node(DependencyNode(node_id="supplier_type", name="Supplier Type"))
    graph.add_edge(DependencyEdge(source_id="supplier", target_id="supplier_type"))
    graph.add_edge(DependencyEdge(source_id="supplier_type", target_id="supplier"))

    service = ImpactAnalysisService()
    cycles = service.detect_circular_dependencies(graph)

    assert cycles[0][0] == "supplier"
    assert len(cycles) == 1


def test_discovers_deep_dependency_chain() -> None:
    graph = DependencyGraph()
    nodes = [
        DependencyNode(node_id="supplier", name="Supplier"),
        DependencyNode(node_id="supplier_type", name="Supplier Type"),
        DependencyNode(node_id="questionnaire", name="Questionnaire"),
        DependencyNode(node_id="workflow", name="Workflow"),
        DependencyNode(node_id="approval", name="Approval"),
        DependencyNode(node_id="notification", name="Notification"),
    ]
    for node in nodes:
        graph.add_node(node)

    graph.add_edge(DependencyEdge(source_id="supplier", target_id="supplier_type"))
    graph.add_edge(DependencyEdge(source_id="supplier_type", target_id="questionnaire"))
    graph.add_edge(DependencyEdge(source_id="questionnaire", target_id="workflow"))
    graph.add_edge(DependencyEdge(source_id="workflow", target_id="approval"))
    graph.add_edge(DependencyEdge(source_id="approval", target_id="notification"))

    service = ImpactAnalysisService()
    dependencies = service.discover_dependencies(graph, "supplier")

    assert [item.node_id for item in dependencies] == ["supplier_type", "questionnaire", "workflow", "approval", "notification"]


def test_analyzes_impact_for_dependent_nodes() -> None:
    graph = DependencyGraph()
    graph.add_node(DependencyNode(node_id="supplier", name="Supplier"))
    graph.add_node(DependencyNode(node_id="supplier_type", name="Supplier Type"))
    graph.add_node(DependencyNode(node_id="questionnaire", name="Questionnaire"))
    graph.add_edge(DependencyEdge(source_id="supplier", target_id="supplier_type"))
    graph.add_edge(DependencyEdge(source_id="supplier_type", target_id="questionnaire"))

    service = ImpactAnalysisService()
    impact = service.analyze_impact(graph, "supplier")

    assert impact["affected_nodes"] == ["supplier_type", "questionnaire"]
    assert impact["has_circular_dependency"] is False


def test_validates_safe_delete_for_dependency_nodes() -> None:
    graph = DependencyGraph()
    graph.add_node(DependencyNode(node_id="supplier_type", name="Supplier Type"))
    graph.add_node(DependencyNode(node_id="questionnaire", name="Questionnaire"))
    graph.add_edge(DependencyEdge(source_id="supplier_type", target_id="questionnaire"))

    service = ImpactAnalysisService()
    validation = service.validate_safe_delete(graph, "supplier_type")

    assert validation["is_safe"] is False
    assert validation["blocking_dependents"] == ["questionnaire"]
