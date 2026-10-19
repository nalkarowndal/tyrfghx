"""M2 orphan-review preview: all decisions are read-only and non-authorizing."""
from __future__ import annotations

import json
from pathlib import Path
import struct

import pytest

from model_catalog import ModelRecord, scan_models
from model_integrity import IntegrityEntry
from model_reconcile_preview import preview_orphan_review
import model_import


def record(**overrides):
    fields = {
        "id": "loras/fixture.safetensors",
        "name": "fixture.safetensors",
        "category": "lora",
        "file_format": "safetensors",
        "size_bytes": 40,
        "validation": "metadata_only",
        "integrity_state": "not_recorded",
        "note": "synthetic metadata only",
    }
    fields.update(overrides)
    return ModelRecord(**fields)


def test_unregistered_mock_only_requires_manual_review():
    result = preview_orphan_review(record(), manifest_ok=True, existing_entry=None)
    assert result.status == "review_required"
    assert result.model_id == "loras/fixture.safetensors"
    assert result.snapshot_sha256 is None
    assert result.requires_human_review
    assert result.can_register is False
    assert result.can_delete is False
    assert result.can_execute is False
    assert result.files_opened is False
    assert result.files_modified is False
    assert result.trusted_provenance_verified is False


@pytest.mark.parametrize(
    ("candidate", "status"), [
        (None, "invalid_observation"),
        (record(validation="invalid_header"), "invalid_candidate"),
        (record(file_format="ckpt", validation="blocked_legacy"), "invalid_candidate"),
        (record(size_bytes=0), "invalid_candidate"),
        (record(id="../outside.safetensors"), "invalid_observation"),
        (record(id="loras/fixture.bin"), "invalid_observation"),
        (record(integrity_state="file_changed"), "invalid_observation"),
        (record(recorded_sha256="a" * 64), "invalid_observation"),
    ],
)
def test_non_eligible_observations_are_never_authorized(candidate, status):
    result = preview_orphan_review(candidate, manifest_ok=True, existing_entry=None)
    assert result.status == status
    assert not any((result.can_register, result.can_delete, result.can_execute))


def test_existing_entry_cannot_be_silently_overwritten():
    saved = IntegrityEntry(sha256="a" * 64, size_bytes=99, mtime_ns=1)
    result = preview_orphan_review(record(), manifest_ok=True, existing_entry=saved)
    assert result.status == "not_an_orphan"
    assert result.snapshot_sha256 == "a" * 64
    assert not result.can_register


def test_invalid_registry_fails_closed_even_for_valid_catalog_record():
    result = preview_orphan_review(record(), manifest_ok=False, existing_entry=None)
    assert result.status == "invalid_manifest"
    assert result.model_id is None
    assert result.snapshot_sha256 is None
    assert not result.can_register


def test_preview_never_opens_paths_or_uses_network(tmp_path, monkeypatch):
    def should_not_open(*args, **kwargs):
        raise AssertionError("read-only preview must not touch filesystem")
    monkeypatch.setattr(Path, "open", should_not_open)
    good = preview_orphan_review(record(), manifest_ok=True, existing_entry=None)
    blocked = preview_orphan_review(record(), manifest_ok=False, existing_entry=None)
    assert good.status == "review_required"
    assert blocked.status == "invalid_manifest"


def test_failed_synthetic_import_catalog_and_preview_require_human(tmp_path, monkeypatch):
    header = json.dumps({"__metadata__": {}}).encode()
    source = tmp_path / "fixture.safetensors"
    source.write_bytes(struct.pack("<Q", len(header)) + header + b"\0\0\0\0")
    root = tmp_path / "models"

    def fail_after_publishing(*args, **kwargs):
        raise OSError("simulated manifest transaction failure")
    monkeypatch.setattr(model_import, "save_manifest_entry", fail_after_publishing)
    with pytest.raises(RuntimeError, match="manual repair"):
        model_import.import_model(source, "loras", root)

    candidate = root / "loras" / source.name
    original = candidate.read_bytes()
    assert not (root / "integrity.json").exists()
    records = [r for r in scan_models(root) if r.id == "loras/fixture.safetensors"]
    assert len(records) == 1
    result = preview_orphan_review(records[0], manifest_ok=True, existing_entry=None)
    assert result.status == "review_required"
    assert result.snapshot_sha256 is None
    assert not result.can_register
    assert candidate.read_bytes() == original
    assert not (root / "integrity.json").exists()
