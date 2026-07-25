"""Metadata cache metrics helpers."""

from __future__ import annotations

from typing import Literal


MetricName = Literal[
    "object_hit",
    "object_miss",
    "field_hit",
    "field_miss",
    "layout_hit",
    "layout_miss",
    "active_layout_hit",
    "active_layout_miss",
    "validation_hit",
    "validation_miss",
    "expression_hit",
    "expression_miss",
    "localization_hit",
    "localization_miss",
    "refreshes",
    "invalidations",
]


def metric_key(metric_name: MetricName) -> str:
    return f"metadata_cache:metrics:{metric_name}"
