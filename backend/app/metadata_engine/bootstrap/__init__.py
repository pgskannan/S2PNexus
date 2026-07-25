"""Metadata bootstrap helpers for the Metadata Engine."""

from app.metadata_engine.bootstrap.registry import (
    MetadataLayoutDefinition,
    MetadataObjectDefinition,
    bootstrap_metadata_registry,
    clear_metadata_registry,
    get_registered_metadata_layouts,
    get_registered_metadata_objects,
    register_metadata_layout,
    register_metadata_object,
)

# Import bootstrap definitions so decorators are registered at import time.
from app.metadata_engine.bootstrap import definitions  # noqa: F401

__all__ = [
    "MetadataObjectDefinition",
    "MetadataLayoutDefinition",
    "bootstrap_metadata_registry",
    "clear_metadata_registry",
    "get_registered_metadata_layouts",
    "get_registered_metadata_objects",
    "register_metadata_layout",
    "register_metadata_object",
]
