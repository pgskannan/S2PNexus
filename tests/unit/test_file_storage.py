"""Unit tests for app.services.file_storage (2026-08-05 GCS-backend fix).

Covers both storage backends:
- Local disk (settings.GCS_BUCKET_NAME unset) -- the original, still-default
  behavior for local dev/tests.
- GCS (settings.GCS_BUCKET_NAME set) -- the fix for Cloud Run, where local
  disk is per-instance ephemeral and a file saved by one request can 404 on
  a later request served by a different instance (confirmed live on
  2026-08-05: a sent registration workbook 404'd on download/import with
  "Workbook file missing on disk").

The google-cloud-storage package isn't required to run these tests: GCS mode
is exercised against a fake google.cloud.storage module injected into
sys.modules, so this suite doesn't depend on real GCS credentials or network
access, and doesn't require the dependency to be installed in every
environment that runs the test suite.
"""

from __future__ import annotations

import importlib
import sys
import types
from uuid import uuid4

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _reset_file_storage_module(monkeypatch, tmp_path):
    """Reload app.services.file_storage fresh for every test.

    Necessary because the module caches a lazy `_gcs_client` singleton at
    module scope -- without a reload, a GCS-mode test could leak its fake
    client into a later local-mode test (or vice versa).
    """
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "GCS_BUCKET_NAME", None)
    sys.modules.pop("app.services.file_storage", None)
    module = importlib.import_module("app.services.file_storage")
    yield module
    sys.modules.pop("app.services.file_storage", None)


def test_local_mode_round_trip_when_bucket_unset(_reset_file_storage_module):
    fs = _reset_file_storage_module
    reg_id = uuid4()
    key = fs.build_key(reg_id, "sent")

    saved_key = fs.save_bytes(key, b"hello workbook")
    assert saved_key == key
    assert fs.load_bytes(key) == b"hello workbook"


def test_local_mode_load_missing_key_raises(_reset_file_storage_module):
    fs = _reset_file_storage_module
    with pytest.raises(FileNotFoundError):
        fs.load_bytes(fs.build_key(uuid4(), "sent"))


def test_local_mode_rejects_path_traversal(_reset_file_storage_module):
    fs = _reset_file_storage_module
    with pytest.raises(ValueError):
        fs.save_bytes("../../etc/passwd", b"nope")


class _FakeBlob:
    def __init__(self, store: dict[str, bytes], name: str):
        self._store = store
        self._name = name

    def upload_from_string(self, data: bytes) -> None:
        self._store[self._name] = data

    def download_as_bytes(self) -> bytes:
        return self._store[self._name]

    def exists(self) -> bool:
        return self._name in self._store


class _FakeBucket:
    def __init__(self, store: dict[str, bytes]):
        self._store = store

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self._store, name)


class _FakeGcsClient:
    """Records the constructor args so the test can assert ADC-style usage
    (project= passed through, no explicit credentials/key file)."""

    instances: list["_FakeGcsClient"] = []

    def __init__(self, project=None):
        self.project = project
        self._store: dict[str, bytes] = {}
        _FakeGcsClient.instances.append(self)

    def bucket(self, name: str) -> _FakeBucket:
        self.bucket_name = name
        return _FakeBucket(self._store)


@pytest.fixture
def fake_gcs_module(monkeypatch):
    """Inject a fake google.cloud.storage module so file_storage's lazy
    `from google.cloud import storage` import succeeds without the real
    package installed."""
    _FakeGcsClient.instances = []
    fake_storage_mod = types.SimpleNamespace(Client=_FakeGcsClient)
    fake_google_cloud_mod = types.ModuleType("google.cloud")
    fake_google_cloud_mod.storage = fake_storage_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.cloud", fake_google_cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", fake_storage_mod)
    yield _FakeGcsClient


def test_gcs_mode_round_trip_when_bucket_set(_reset_file_storage_module, fake_gcs_module, monkeypatch):
    monkeypatch.setattr(settings, "GCS_BUCKET_NAME", "s2pnexus-registrations")
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_PROJECT", "s2pnexus")
    fs = _reset_file_storage_module
    reg_id = uuid4()
    key = fs.build_key(reg_id, "sent")

    fs.save_bytes(key, b"gcs workbook bytes")
    assert fs.load_bytes(key) == b"gcs workbook bytes"

    # ADC usage: client constructed with just the project, no key file.
    assert len(fake_gcs_module.instances) == 1
    client = fake_gcs_module.instances[0]
    assert client.project == "s2pnexus"
    assert client.bucket_name == "s2pnexus-registrations"


def test_gcs_mode_load_missing_key_raises(_reset_file_storage_module, fake_gcs_module, monkeypatch):
    monkeypatch.setattr(settings, "GCS_BUCKET_NAME", "s2pnexus-registrations")
    fs = _reset_file_storage_module
    with pytest.raises(FileNotFoundError):
        fs.load_bytes(fs.build_key(uuid4(), "sent"))


def test_gcs_mode_reuses_single_client_across_calls(_reset_file_storage_module, fake_gcs_module, monkeypatch):
    """The client is a lazy singleton -- shouldn't reconstruct on every call."""
    monkeypatch.setattr(settings, "GCS_BUCKET_NAME", "s2pnexus-registrations")
    fs = _reset_file_storage_module
    reg_id = uuid4()
    fs.save_bytes(fs.build_key(reg_id, "sent"), b"a")
    fs.save_bytes(fs.build_key(reg_id, "returned"), b"b")
    fs.load_bytes(fs.build_key(reg_id, "sent"))

    assert len(fake_gcs_module.instances) == 1


def test_local_disk_untouched_in_gcs_mode(_reset_file_storage_module, fake_gcs_module, monkeypatch, tmp_path):
    """When GCS mode is active, bytes must not also land on local disk --
    otherwise this would silently work in single-instance local testing but
    still be broken in the real multi-instance Cloud Run environment."""
    monkeypatch.setattr(settings, "GCS_BUCKET_NAME", "s2pnexus-registrations")
    fs = _reset_file_storage_module
    reg_id = uuid4()
    fs.save_bytes(fs.build_key(reg_id, "sent"), b"gcs only")

    assert not (tmp_path / "supplier_registrations" / str(reg_id)).exists()
