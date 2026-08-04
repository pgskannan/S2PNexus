"""Loader for the email template catalog (backlog Section 1).

``backend/app/templates/email/templates_catalog.json`` is the single source of
truth for every lifecycle email's default subject / HTML / text / variables /
tenant_overridable flag. This module reads it (the catalog was previously a
dead file — nothing consumed it), so the admin router can merge catalog
defaults with any active ``EmailTemplateOverride`` row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# backend/app/templates/email/templates_catalog.json
CATALOG_PATH = Path(__file__).resolve().parent.parent / "templates" / "email" / "templates_catalog.json"

_catalog_cache: list[dict[str, Any]] | None = None


def load_catalog() -> list[dict[str, Any]]:
    """Return the full catalog as a list of entry dicts (cached)."""
    global _catalog_cache
    if _catalog_cache is None:
        with open(CATALOG_PATH, encoding="utf-8") as fh:
            _catalog_cache = json.load(fh)
    return _catalog_cache


def get_catalog_entry(email_type: str) -> dict[str, Any] | None:
    """Return the catalog entry matching an ``email_type`` (e.g. ``po.dispatch``)."""
    for entry in load_catalog():
        if entry.get("email_type") == email_type:
            return entry
    return None


def list_email_types() -> list[str]:
    return [entry["email_type"] for entry in load_catalog()]
