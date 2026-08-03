"""Local filesystem storage for supplier registration workbooks (FS 13.1/16.5).

Scope note (see docs/PR_AUDIT_QUICK_WINS_2026-08-02.md item 5 and the storage
audit in docs/FABLE5_SUPPLIER_TYPE_EXCEL_REGISTRATION_PROMPT.md): this repo
has no real object-storage client wired anywhere. `ProcurementAttachment.
storage_key` has had the exact same "where do the bytes actually live" gap
since it was added. This module deliberately does NOT fix that older gap --
it only wires local-filesystem storage for the *new* Excel registration
artifacts (sent workbook, returned workbook, ErrorReport, ImportSummary).
Extending this abstraction to ProcurementAttachment (or swapping this whole
module for S3/GCS) is left for a dedicated follow-up so it can be reviewed on
its own, not smuggled in as a side effect of the registration feature.

Layout: {settings.UPLOAD_DIR}/supplier_registrations/{registration_id}/<file>

Keys returned by save_bytes()/build_key() are always relative to UPLOAD_DIR
(never absolute), so they're safe to persist in a DB column (e.g.
SupplierRegistration.sent_workbook_path) that might point at a different
storage root in another environment without a data migration.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import settings

_REGISTRATIONS_SUBDIR = "supplier_registrations"

# kind -> filename. FS 15.4/16.5 name ErrorReport.xlsx/ImportSummary.txt
# explicitly; the sent/returned workbook names are this batch's own
# convention (the FS doesn't specify them).
_KIND_FILENAMES = {
    "sent": "SentWorkbook.xlsx",
    "returned": "ReturnedWorkbook.xlsx",
    "error_report": "ErrorReport.xlsx",
    "import_summary": "ImportSummary.txt",
}


def _upload_root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


def registration_dir(registration_id: UUID | str) -> Path:
    """Absolute directory holding every stored artifact for one registration."""
    return _upload_root() / _REGISTRATIONS_SUBDIR / str(registration_id)


def build_key(registration_id: UUID | str, kind: str) -> str:
    """Relative storage key for one of the well-known registration artifacts.

    `kind` is one of "sent", "returned", "error_report", "import_summary".
    """
    if kind not in _KIND_FILENAMES:
        raise ValueError(f"Unknown storage kind {kind!r}; expected one of {sorted(_KIND_FILENAMES)}")
    return f"{_REGISTRATIONS_SUBDIR}/{registration_id}/{_KIND_FILENAMES[kind]}"


def _resolve_relative_key(relative_key: str) -> Path:
    """Resolve a relative key to an absolute path, rejecting path traversal.

    Keys are generated exclusively by build_key() in this codebase, but this
    guard still protects against a corrupted or hand-edited DB value ever
    resolving outside UPLOAD_DIR (e.g. "../../etc/passwd").
    """
    root = _upload_root()
    candidate = (root / relative_key).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Storage key {relative_key!r} escapes UPLOAD_DIR")
    return candidate


def save_bytes(relative_key: str, data: bytes) -> str:
    """Write bytes under UPLOAD_DIR, creating parent directories as needed.

    Returns the same relative_key back, so callers can chain
    `path = save_bytes(build_key(reg.id, "sent"), xlsx_bytes)`.
    """
    path = _resolve_relative_key(relative_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relative_key


def load_bytes(relative_key: str) -> bytes:
    """Read bytes previously written by save_bytes()."""
    path = _resolve_relative_key(relative_key)
    if not path.is_file():
        raise FileNotFoundError(f"No stored file at key {relative_key!r}")
    return path.read_bytes()
