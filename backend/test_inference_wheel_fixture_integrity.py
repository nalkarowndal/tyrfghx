"""M4-1e synthetic-only local wheel bytes integrity regression tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from inference_install_preview import PlanReject
from inference_wheel_fixture_integrity import (
    FIXTURE_MARKER,
    MARKER_BYTES,
    MAX_FIXTURE_BYTES,
    verify_synthetic_fixture,
)

NAME = "torch-2.6.0+cu124-cp312-cp312-win_amd64.whl"
SAMPLE = b"synthetic wheel-like bytes; not an installable wheel\n"


def manifest(payload: bytes = SAMPLE, *, digest: str | None = None,
             size: int | None = None, filename: str = NAME) -> bytes:
    return json.dumps({
        "schema_version": 1,
        "platform": "windows_x86_64",
        "python_version": "3.12",
        "destination_kind": "user_selected_private_venv",
        "wheels": [{
            "package": "torch",
            "version": "2.6.0+cu124",
            "filename": filename,
            "sha256": digest if digest is not None else hashlib.sha256(payload).hexdigest(),
            "declared_bytes": size if size is not None else len(payload),
        }],
    }).encode("utf-8")


def fixture(root: Path, *, payload: bytes = SAMPLE) -> Path:
    root.mkdir()
    (root / FIXTURE_MARKER).write_bytes(MARKER_BYTES)
    (root / NAME).write_bytes(payload)
    return root


def test_exact_synthetic_bytes_are_hashed_but_cannot_enable_install(tmp_path):
    root = fixture(tmp_path / "isolated")
    report = verify_synthetic_fixture(manifest(), root)
    assert report["status"] == "synthetic_fixture_verified"
    assert report["synthetic_fixture"] is True
    assert report["checked_count"] == 1
    assert report["all_fixture_hashes_match"] is True
    for flag in ("wheel_archive_validated", "wheel_compatibility_verified",
                 "source_provenance_verified", "production_path_safe",
                 "user_files_touched", "downloads_performed", "packages_installed",
                 "gpu_accessed", "execution_enabled"):
        assert report[flag] is False
    assert (root / NAME).read_bytes() == SAMPLE
    json.dumps(report)


@pytest.mark.parametrize("kind", ["tampered", "missing", "wrong_size", "wrong_hash", "oversized"])
def test_missing_tampered_wrong_size_and_large_mock_are_rejected(tmp_path, kind):
    root = fixture(tmp_path / "isolated")
    frame = manifest()
    if kind == "tampered":
        (root / NAME).write_bytes(SAMPLE[::-1])
    elif kind == "missing":
        (root / NAME).unlink()
    elif kind == "wrong_size":
        frame = manifest(size=len(SAMPLE) + 1)
    elif kind == "wrong_hash":
        frame = manifest(digest="a" * 64)
    elif kind == "oversized":
        frame = manifest(size=MAX_FIXTURE_BYTES + 1)
    report = verify_synthetic_fixture(frame, root)
    assert report["status"] == "synthetic_fixture_rejected"
    assert report["all_fixture_hashes_match"] is False
    assert report["execution_enabled"] is False


def test_directory_and_wrong_marker_cannot_be_treated_as_fixture(tmp_path):
    absent = tmp_path / "missing"
    assert verify_synthetic_fixture(manifest(), absent)["status"] == "synthetic_fixture_rejected"
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    (unmarked / NAME).write_bytes(SAMPLE)
    assert verify_synthetic_fixture(manifest(), unmarked)["status"] == "synthetic_fixture_rejected"
    (unmarked / FIXTURE_MARKER).write_bytes(b"not a fixture")
    assert verify_synthetic_fixture(manifest(), unmarked)["status"] == "synthetic_fixture_rejected"
    (unmarked / FIXTURE_MARKER).write_bytes(MARKER_BYTES)
    assert verify_synthetic_fixture(manifest(), unmarked)["status"] == "synthetic_fixture_verified"


def test_symlinked_file_never_opens_external_bytes(tmp_path):
    root = fixture(tmp_path / "isolated")
    outside = tmp_path / "outside"
    outside.write_bytes(SAMPLE)
    (root / NAME).unlink()
    try:
        (root / NAME).symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Windows runner does not allow developer-mode symlink creation")
    report = verify_synthetic_fixture(manifest(), root)
    assert report["status"] == "synthetic_fixture_rejected"
    assert outside.read_bytes() == SAMPLE


def test_symlinked_fixture_root_is_denied(tmp_path):
    real_root = fixture(tmp_path / "isolated")
    alias = tmp_path / "shortcut"
    try:
        alias.symlink_to(real_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Windows runner does not allow symlink creation")
    assert verify_synthetic_fixture(manifest(), alias)["status"] == "synthetic_fixture_rejected"


def test_path_in_manifest_does_not_override_fixture_root(tmp_path):
    root = fixture(tmp_path / "isolated")
    for name in ("../evil.whl", "C:\\private\\target.whl",
                 "https://example.com/target.whl", NAME + "/.."):
        with pytest.raises(PlanReject, match="^invalid_manifest$"):
            verify_synthetic_fixture(manifest(filename=name), root)


def test_invalid_frame_is_rejected_before_filesystem_access(tmp_path):
    with pytest.raises(PlanReject, match="^invalid_manifest$"):
        verify_synthetic_fixture(b"not-json", tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_cancellation_never_reads_fixture_or_invalid_manifest(tmp_path):
    report = verify_synthetic_fixture(b"invalid", tmp_path / "missing", cancelled=True)
    assert report == {"status": "cancelled", "side_effects_performed": False}
    with pytest.raises(PlanReject, match="^invalid_options$"):
        verify_synthetic_fixture(manifest(), tmp_path, cancelled=1)


def test_normal_fixture_hashing_uses_no_cuda_installer_or_route(tmp_path):
    from app import create_app
    assert not any("wheel" in p or "install" in p for p in create_app().openapi()["paths"])
    code = (Path(__file__).parent / "inference_wheel_fixture_integrity.py").read_text("utf-8")
    for forbidden in ("import torch", "import diffusers", "import subprocess",
                      "import requests", "import socket", "Popen(", "os.system(", "pip install"):
        assert forbidden not in code
    root = fixture(tmp_path / "isolated")
    assert verify_synthetic_fixture(manifest(), root)["execution_enabled"] is False
