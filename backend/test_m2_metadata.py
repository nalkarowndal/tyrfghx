import json
import struct

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app as app_module
from model_catalog import scan_models
from model_compatibility import evaluate_pair
from model_metadata import ModelAnnotation, infer_family, read_annotations, save_annotation, valid_id


def write_model(path, arch=None):
    meta = {"modelspec.architecture": arch} if arch else {}
    payload = json.dumps({"__metadata__": meta}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(payload)) + payload)


@pytest.fixture
def model_root(tmp_path):
    for name in ("checkpoints", "loras", "vae"):
        (tmp_path / name).mkdir()
    write_model(tmp_path / "checkpoints" / "sdxl.safetensors", "stable-diffusion-xl-v1-base")
    write_model(tmp_path / "checkpoints" / "sd15.safetensors", "stable-diffusion-v1")
    write_model(tmp_path / "loras" / "style.safetensors")
    write_model(tmp_path / "vae" / "decoder.safetensors")
    return tmp_path


@pytest.mark.parametrize("value", [
    "../escape.safetensors", "checkpoints/../../escape.safetensors",
    "loras\\evil.safetensors", "loras/a\\b.safetensors", "vae/x.ckpt",
    "downloads/model.safetensors", "loras/C:/abc.safetensors",
])
def test_registry_rejects_invalid_ids(value):
    assert not valid_id(value)


def test_metadata_cli_registration_and_sources(model_root):
    save_annotation(model_root, "loras/style.safetensors", ModelAnnotation(
        display_name="My style", family_override="sdxl",
        license="creator license", notes="tested only in metadata catalog"))
    items = scan_models(model_root)
    lora = next(item for item in items if item.id == "loras/style.safetensors")
    assert lora.display_name == "My style"
    assert lora.family == "sdxl"
    assert lora.family_source == "manual"
    assert lora.license == "creator license"
    assert "model_root" not in json.dumps(lora.model_dump())
    assert next(item for item in items if item.id == "checkpoints/sdxl.safetensors").family_source == "header"


def test_rejects_registry_symlinks_and_escape(model_root, tmp_path):
    outside = tmp_path.parent / "outside.safetensors"
    write_model(outside)
    with pytest.raises(ValueError):
        save_annotation(model_root, "../outside.safetensors", ModelAnnotation())
    path = model_root / "loras" / "escaped.safetensors"
    try:
        path.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError):
        save_annotation(model_root, "loras/escaped.safetensors", ModelAnnotation())


def test_missing_and_malformed_registry_safe(model_root):
    bad_registry = model_root / "annotations.json"
    bad_registry.write_text("{broken", encoding="utf-8")
    assert read_annotations(model_root) == {}
    assert len(scan_models(model_root)) == 4


def test_annotation_input_validation():
    with pytest.raises(ValidationError):
        ModelAnnotation(display_name="x" * 300)
    with pytest.raises(ValidationError):
        ModelAnnotation(family_override="unknown")
    with pytest.raises(ValidationError):
        ModelAnnotation(extra_unknown_field="bad")


def test_no_filename_guessing():
    assert infer_family("some-model-Illustrious") is None
    assert infer_family("Anima") is None
    assert infer_family("stable-diffusion-xl-v1-base") == "sdxl"


def test_candidate_and_mismatch_and_unknown(model_root):
    save_annotation(model_root, "loras/style.safetensors", ModelAnnotation(family_override="sdxl"))
    records = scan_models(model_root)
    assert evaluate_pair(records, "checkpoints/sdxl.safetensors", "loras/style.safetensors").status == "possible_match"
    assert evaluate_pair(records, "checkpoints/sd15.safetensors", "loras/style.safetensors").status == "family_mismatch"
    assert evaluate_pair(records, "checkpoints/sdxl.safetensors", "vae/decoder.safetensors").status == "invalid_selection"
    assert evaluate_pair(records, "checkpoints/none.safetensors", "loras/style.safetensors").status == "not_found"


def test_api_pair_does_not_disclose_paths(monkeypatch, model_root):
    save_annotation(model_root, "loras/style.safetensors", ModelAnnotation(family_override="sdxl"))
    monkeypatch.setattr(app_module, "MODEL_ROOT", model_root)
    client = TestClient(app_module.app)
    res = client.get("/api/models/compatibility", params={
        "checkpoint_id": "checkpoints/sdxl.safetensors", "lora_id": "loras/style.safetensors"})
    assert res.status_code == 200
    assert res.json()["status"] == "possible_match"
    assert str(model_root) not in res.text
    assert client.get("/api/models/compatibility").status_code == 422
