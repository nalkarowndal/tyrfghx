"""Regression tests for PR #1 cooperative importer races: only tiny temp fixtures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import struct
import threading

import pytest

import model_import
import model_manifest_lock
from model_import import import_model
from model_integrity import IntegrityEntry, read_manifest, save_manifest_entry


def fake_safetensors(path, marker):
    header = json.dumps({"__metadata__": {"modelspec.architecture": marker}}).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\x00" * 4)
    return path


def test_concurrent_python_imports_preserve_all_registry_entries(tmp_path):
    roots = [fake_safetensors(tmp_path / f"source_{i}.safetensors", f"sample_{i}")
             for i in range(6)]
    store = tmp_path / "models"
    go = threading.Barrier(len(roots))
    def do_import(index):
        go.wait(timeout=5)
        return import_model(roots[index], "loras", store)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(do_import, range(len(roots))))
    registry = read_manifest(store, strict=True)
    assert set(registry) == {f"loras/{p.name}" for p in roots}
    for key, sha in results:
        assert registry[key].sha256 == sha
        assert (store / key).is_file()
    assert not (store / model_manifest_lock.LOCK_NAME).exists()


def test_concurrent_metadata_writes_are_serialized(tmp_path):
    store = tmp_path / "models"
    store.mkdir()
    entries = [
        (f"checkpoints/dummy_{i}.safetensors",
         IntegrityEntry(sha256=f"{i:064x}", size_bytes=i, mtime_ns=i))
        for i in range(12)
    ]
    gate = threading.Barrier(6)
    def persist(pair):
        gate.wait(timeout=5)
        save_manifest_entry(store, *pair)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(persist, entries[:6]))
    for pair in entries[6:]:
        save_manifest_entry(store, *pair)
    assert set(read_manifest(store, strict=True)) == {key for key, _ in entries}


def test_source_path_swap_after_open_keeps_original_validated_bytes(tmp_path, monkeypatch):
    source = fake_safetensors(tmp_path / "source.safetensors", "original")
    original = source.read_bytes()
    replacement = tmp_path / "replacement.safetensors"
    fake_safetensors(replacement, "changed")
    replacement_bytes = replacement.read_bytes()
    ordinary = model_import.tempfile.NamedTemporaryFile
    flipped = {"value": False}

    def before_stage(*args, **kwargs):
        if not flipped["value"]:
            flipped["value"] = True
            try:
                source.unlink()
                replacement.rename(source)
            except PermissionError:
                # Windows file sharing may forbid removal of an open file;
                # this is a platform protection, not evidence of a swap.
                pytest.skip("Windows denies replacement of open fixture")
        return ordinary(*args, **kwargs)

    monkeypatch.setattr(model_import.tempfile, "NamedTemporaryFile", before_stage)
    model_id, digest = import_model(source, "checkpoints", tmp_path / "models")
    assert flipped["value"] is True
    assert source.read_bytes() == replacement_bytes
    assert (tmp_path / "models" / model_id).read_bytes() == original
    assert digest == hashlib.sha256(original).hexdigest()


def test_failed_manifest_registration_never_unlinks_replaced_target(tmp_path, monkeypatch):
    source = fake_safetensors(tmp_path / "source.safetensors", "test")
    root = tmp_path / "models"
    marker = b"some-other-process-owns-this-path"

    def hostile_failing_registry(*args, **kwargs):
        target = root / "loras" / source.name
        assert target.exists()
        target.unlink()
        target.write_bytes(marker)
        raise OSError("fixture registry unavailable")

    monkeypatch.setattr(model_import, "save_manifest_entry", hostile_failing_registry)
    with pytest.raises(RuntimeError, match="copy retained"):
        import_model(source, "loras", root)
    assert (root / "loras" / source.name).read_bytes() == marker
    assert not (root / "integrity.json").exists()


def test_stale_lock_fails_closed_without_deleting_other_lock(tmp_path, monkeypatch):
    root = tmp_path / "models"
    root.mkdir()
    guard = root / model_manifest_lock.LOCK_NAME
    guard.mkdir()
    monkeypatch.setattr(model_manifest_lock, "LOCK_TIMEOUT_SEC", 0.06)
    with pytest.raises(ValueError, match="busy"):
        save_manifest_entry(
            root, "loras/a.safetensors",
            IntegrityEntry(sha256="f" * 64, size_bytes=10, mtime_ns=1))
    assert guard.is_dir()
    assert not (root / "integrity.json").exists()


def test_corrupt_manifest_preflight_does_not_publish_file(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "integrity.json").write_text("{broken", encoding="utf-8")
    source = fake_safetensors(tmp_path / "valid.safetensors", "test")
    with pytest.raises(ValueError, match="damaged"):
        import_model(source, "loras", root)
    assert not (root / "loras" / source.name).exists()


def test_orphaned_valid_synthetic_copy_remains_untrusted_and_read_only(tmp_path, monkeypatch):
    """After a registry-write failure, catalog never trusts/repairs an orphan."""
    from model_catalog import scan_models

    source = fake_safetensors(tmp_path / "orphan.safetensors", "fixture")
    root = tmp_path / "models"
    def force_manifest_failure(*_args, **_kwargs):
        raise OSError("synthetic transaction failure")

    monkeypatch.setattr(model_import, "save_manifest_entry", force_manifest_failure)
    with pytest.raises(RuntimeError, match="manual repair"):
        import_model(source, "loras", root)
    target = root / "loras" / source.name
    before = target.read_bytes()
    assert before == source.read_bytes()
    assert not (root / "integrity.json").exists()
    records = scan_models(root)
    matches = [record for record in records if record.id == f"loras/{source.name}"]
    assert len(matches) == 1
    assert matches[0].integrity_state == "not_recorded"
    assert matches[0].recorded_sha256 is None
    assert matches[0].validation == "metadata_only"
    assert target.read_bytes() == before
    assert not (root / "integrity.json").exists()
