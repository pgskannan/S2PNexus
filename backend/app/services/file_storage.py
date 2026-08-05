"""Storage for supplier registration workbooks (FS 13.1/16.5).

Scope note (see docs/PR_AUDIT_QUICK_WINS_2026-08-02.md item 5 and the storage
audit in docs/FABLE5_SUPPLIER_TYPE_EXCEL_REGISTRATION_PROMPT.md): this repo
has no real object-storage client wired anywhere else. `ProcurementAttachment.
storage_key` has had the exact same "where do the bytes actually live" gap
since it was added. This module deliberately does NOT fix that older gap --
it only wires storage for the *new* Excel registration artifacts (sent
workbook, returned workbook, ErrorReport, ImportSummary). Extending this
abstraction to ProcurementAttachment is left for a dedicated follow-up so it
can be reviewed on its own, not smuggled in as a side effect here.

Backend selection (2026-08-05 fix): this originally only wrote to local disk
under UPLOAD_DIR, which works for local dev/tests but is broken on Cloud Run
-- each revision can run multiple instances and gets recycled, and instance
-local disk is not shared or durable, so a workbook saved by one request
could 404 on a later request served by a different instance (confirmed live:
"Send" succeeded, a later "Download"/import 404'd with "Workbook file
missing on disk" against a fresh instance). When `settings.GCS_BUCKET_NAME`
is set, this module reads/writes Google Cloud Storage instead, using
Application Default Credentials (the Cloud Run service account -- no
separate key needed since GOOGLE_CLOUD_PROJECT is already configured for
Vertex AI). Local disk remains the fallback when GCS_BUCKET_NAME is unset,
which keeps local dev and the existing test suite working unchanged.

Layout / GCS object naming: {settings.UPLOAD_DIR}/supplier_registrations/{registration_id}/<file>
(local) or the same relative path as a GCS blob name (bucket mode).

Keys returned by save_bytes()/build_key() are always relative (never
absolute local paths, never a gs:// URI), so they're safe to persist in a DB
column (e.g. SupplierRegistration.sent_workbook_path) that might point at a
different storage root/bucket in another environment without a data
migration.
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

_gcs_client = None  # lazy singleton -- only constructed if GCS_BUCKET_NAME is actually set


def _use_gcs() -> bool:
    return bool(settings.GCS_BUCKET_NAME)


def _gcs_bucket():
    """Lazily construct (and cache) the GCS client/bucket handle.

    Imported lazily so `google-cloud-storage` is only required at runtime
    when GCS mode is actually enabled -- local dev/tests never need it.
    """
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage

        _gcs_client = storage.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
    return _gcs_client.bucket(settings.GCS_BUCKET_NAME)


def _upload_root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


def registration_dir(registration_id: UUID | str) -> Path:
    """Absolute local directory holding one registration's artifacts.

    Only meaningful in local-disk mode (GCS_BUCKET_NAME unset); kept for
    local dev/debugging convenience.
    """
    return _upload_root() / _REGISTRATIONS_SUBDIR / str(registration_id)


def build_key(registration_id: UUID | str, kind: str) -> str:
    """Relative storage key for one of the well-known registration artifacts.

    `kind` is one of "sent", "returned", "error_report", "import_summary".
    Used as either a local path (relative to UPLOAD_DIR) or a GCS blob name,
    depending on the active backend.
    """
    if kind not in _KIND_FILENAMES:
        raise ValueError(f"Unknown storage kind {kind!r}; expected one of {sorted(_KIND_FILENAMES)}")
    return f"{_REGISTRATIONS_SUBDIR}/{registration_id}/{_KIND_FILENAMES[kind]}"


def _resolve_relative_key(relative_key: str) -> Path:
    """Resolve a relative key to an absolute local path, rejecting path traversal.

    Keys are generated exclusively by build_key() in this codebase, but this
    guard still protects against a corrupted or hand-edited DB value ever
    resolving outside UPLOAD_DIR (e.g. "../../etc/passwd"). Local-disk mode
    only.
    """
    root = _upload_root()
    candidate = (root / relative_key).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Storage key {relative_key!r} escapes UPLOAD_DIR")
    return candidate


def save_bytes(relative_key: str, data: bytes) -> str:
    """Write bytes under the active backend (GCS bucket or local UPLOAD_DIR).

    Returns the same relative_key back, so callers can chain
    `path = save_bytes(build_key(reg.id, "sent"), xlsx_bytes)`.
    """
    if _use_gcs():
        _gcs_bucket().blob(relative_key).upload_from_string(data)
        return relative_key
    path = _resolve_relative_key(relative_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relative_key


def load_bytes(relative_key: str) -> bytes:
    """Read bytes previously written by save_bytes() from the active backend."""
    if _use_gcs():
        blob = _gcs_bucket().blob(relative_key)
        if not blob.exists():
            raise FileNotFoundError(f"No stored file at key {relative_key!r}")
        return blob.download_as_bytes()
    path = _resolve_relative_key(relative_key)
    if not path.is_file():
        raise FileNotFoundError(f"No stored file at key {relative_key!r}")
    return path.read_bytes()
