"""Compatibility shim for structured logging helpers."""

from app.core.logging import get_logger, setup_logging

__all__ = ["get_logger", "setup_logging"]
