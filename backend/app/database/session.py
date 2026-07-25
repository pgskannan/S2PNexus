"""Compatibility shim for the database session dependency."""

from app.database.database import get_db

__all__ = ["get_db"]
