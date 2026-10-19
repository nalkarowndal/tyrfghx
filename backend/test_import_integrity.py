"""Import and integrity tests use tiny synthetic safetensors headers only."""
import hashlib
import json
import os
import struct

import pytest

from model_catalog import scan_models
from model_import import import_model
from model_integrity import (
    IntegrityEntry, hash_model, integrity_state, read_manifest, save_manifest_entry,
    verify_model,
)


def model_file(path, arch="stable-diffusion-xl-v1-base"):
    header = json.dumps({"__metadata__": {"modelspec.architecture": arch}}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\x00\x00\x00\x00")
    return path


def test_import_creates_snapshot_without_touching_source(tmp_path):
    source = model_file(tmp_path / "download.safetensors")
    original = source.read_bytes()
    root = tmp_path / "models"
    identifier, digest = import_model(source, "checkpoints", root)
    assert identifier == "checkpoints/download.safetensors"
    assert source.read_bytes() == original
    assert (root / identifier).read_bytes() == original
    assert digest == hashlib.sha256(original).hexdigest()
    assert read_manifest(root)[identifier].sha256 == digest
    assert verify_model(root, identifier) == ("match", digest)
    catalog = scan_models(root)
    assert len(catalog) == 1
    assert catalog[0].integrity_state == "snapshot_unchanged"
    assert catalog[0].recorded_sha256 == digest


def test_reject_collision_without_overwrite(tmp_path):
    source = model_file(tmp_path / "dup.safetensors")
    root = tmp_path / "models"
    import_model(source, "loras", root)
    original = (root / "loras" / "dup.safetensors").read_bytes()
    with pytest.raises(FileExistsError):
        import_model(source, "loras", root)
    assert (root / "loras" / "dup.safetensors").read_bytes() == original


def test_bad_hash_does_not_import(tmp_path):
    source = model_file(tmp_path / "wrong.safetensors")
    root = tmp_path / "models"
    with pytest.raises(ValueError, match="does not match"):
        import_model(source, "vae", root, expected_sha256="0" * 64)
    assert not (root / "vae" / source.name).exists()
    assert not (root / "integrity.json").exists()


def test_invalid_header_rejected(tmp_path):
    source = tmp_path / "broken.safetensors"
    source.write_bytes(struct.pack("<Q", 1_000_000) + b"{}")
    with pytest.raises(ValueError, match="header"):
        import_model(source, "loras", tmp_path / "models")


def test_reject_ckpt_and_symlink(tmp_path):
    ckpt = tmp_path / "risk.ckpt"
    ckpt.write_bytes(b"pickle")
    with pytest.raises(ValueError):
        import_model(ckpt, "checkpoints", tmp_path / "models")
    source = model_file(tmp_path / "real.safetensors")
    link = tmp_path / "alias.safetensors"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError):
        import_model(link, "checkpoints", tmp_path / "models")


def test_verify_detects_change_and_does_not_refresh_manifest(tmp_path):
    source = model_file(tmp_path / "file.safetensors")
    root = tmp_path / "models"
    model_id, digest = import_model(source, "checkpoints", root)
    target = root / model_id
    target.write_bytes(target.read_bytes() + b"change")
    assert verify_model(root, model_id)[0] == "mismatch"
    assert scan_models(root)[0].integrity_state == "file_changed"
    assert read_manifest(root)[model_id].sha256 == digest


def test_no_checksum_for_manual_file(tmp_path):
    root = tmp_path / "models"
    folder = root / "vae"
    folder.mkdir(parents=True)
    model_file(folder / "manual.safetensors")
    assert scan_models(root)[0].integrity_state == "not_recorded"
    assert scan_models(root)[0].recorded_sha256 is None
    assert verify_model(root, "vae/manual.safetensors")[0] == "unrecorded"


def test_broken_manifest_not_overwritten(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "integrity.json").write_text("{bad", encoding="utf-8")
    source = model_file(tmp_path / "new.safetensors")
    with pytest.raises(ValueError, match="damaged"):
        import_model(source, "loras", root)
    assert (root / "integrity.json").read_text() == "{bad"
    assert not (root / "loras" / "new.safetensors").exists()


def test_duplicate_identification_is_hint_only(tmp_path):
    source = model_file(tmp_path / "original.safetensors")
    root = tmp_path / "models"
    first, digest = import_model(source, "checkpoints", root)
    renamed = model_file(tmp_path / "second.safetensors")
    second, digest2 = import_model(renamed, "vae", root)
    assert digest == digest2
    items = scan_models(root)
    assert next(x for x in items if x.id == first).potential_duplicate_ids == [second]
    assert next(x for x in items if x.id == second).potential_duplicate_ids == [first]


def test_manifest_symlink_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    external = tmp_path / "external.json"
    external.write_text("{}")
    target = root / "integrity.json"
    try:
        target.symlink_to(external)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError):
        save_manifest_entry(root, "loras/x.safetensors", IntegrityEntry(sha256="a" * 64, size_bytes=12, mtime_ns=0))
