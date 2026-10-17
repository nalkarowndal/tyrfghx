import json
import struct

import app as app_module
from fastapi.testclient import TestClient
from model_catalog import scan_models


def write_safetensors(path, metadata=None):
    header = json.dumps({"__metadata__": metadata or {}}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header)


def test_empty_root(tmp_path):
    assert scan_models(tmp_path) == []


def test_catalog_does_not_execute_weights_and_detects_metadata(tmp_path):
    checkpoints = tmp_path / "checkpoints"
    loras = tmp_path / "loras"
    vae = tmp_path / "vae"
    for folder in (checkpoints, loras, vae):
        folder.mkdir()
    write_safetensors(checkpoints / "model.safetensors",
                      {"modelspec.architecture": "stable-diffusion-xl-v1-base"})
    write_safetensors(loras / "style.safetensors")
    write_safetensors(vae / "vae.safetensors")
    (checkpoints / "unsafe.ckpt").write_bytes(b"not-a-model")
    (checkpoints / "script.py").write_text("raise RuntimeError('should never execute')")
    items = scan_models(tmp_path)
    assert len(items) == 4
    assert [x.category for x in items] == ["checkpoint", "checkpoint", "lora", "vae"]
    verified = next(x for x in items if x.name == "model.safetensors")
    assert verified.reported_architecture == "stable-diffusion-xl-v1-base"
    assert verified.validation == "metadata_only"
    legacy = next(x for x in items if x.name == "unsafe.ckpt")
    assert legacy.validation == "blocked_legacy"
    assert all(not x.id.startswith("/") for x in items)


def test_malformed_header_is_not_claimed_to_work(tmp_path):
    folder = tmp_path / "loras"
    folder.mkdir()
    (folder / "broken.safetensors").write_bytes(struct.pack("<Q", 2_000_000) + b"{}")
    item = scan_models(tmp_path)[0]
    assert item.validation == "invalid_header"
    assert item.reported_architecture is None


def test_symlink_file_is_ignored(tmp_path):
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    external = tmp_path / "outside.safetensors"
    write_safetensors(external)
    link = folder / "linked.safetensors"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        return
    assert scan_models(tmp_path) == []


def test_endpoint_returns_inventory_without_absolute_paths(monkeypatch, tmp_path):
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    write_safetensors(folder / "sample.safetensors")
    monkeypatch.setattr(app_module, "MODEL_ROOT", tmp_path)
    response = TestClient(app_module.app).get("/api/models")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "checkpoints/sample.safetensors"
    assert str(tmp_path) not in response.text
