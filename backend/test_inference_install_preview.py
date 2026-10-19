"""M4-1d deterministic offline-preview and denial-of-execution tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from inference_install_preview import MAX_BYTES, PlanReject, preview

_SAMPLE = {
    "schema_version": 1,
    "platform": "windows_x86_64",
    "python_version": "3.12",
    "destination_kind": "user_selected_private_venv",
    "wheels": [{
        "package": "torch",
        "version": "2.6.0+cu124",
        "filename": "torch-2.6.0+cu124-cp312-cp312-win_amd64.whl",
        "sha256": "a" * 64,
        "declared_bytes": 125_000_000,
    }],
}


def data(**changes):
    item = {**_SAMPLE, **changes}
    return json.dumps(item).encode("utf-8")


def invalid(payload):
    with pytest.raises(PlanReject, match="^invalid_manifest$") as error:
        preview(payload)
    assert str(error.value) == "invalid_manifest"


def test_preview_is_non_executable_even_if_capacity_appears_sufficient():
    out = preview(data(), available_bytes=20 * 1024**3)
    assert out["status"] == "blocked_pending_explicit_approval"
    assert out["reported_capacity"] == "reported_sufficient_unverified"
    assert out["provisional_storage_estimate_bytes"] == 3 * 125_000_000 + 2 * 1024**3
    assert out["candidate_count"] == 1
    assert out["packages"] == ["torch"]
    assert all(out[key] is False for key in (
        "estimate_is_verified", "source_provenance_verified", "hashes_verified",
        "wheel_compatibility_verified", "dependencies_verified", "target_path_verified",
        "runtime_verified", "user_approval_granted", "files_opened",
        "downloads_performed", "packages_installed", "gpu_accessed", "execution_enabled",
    ))
    json.dumps(out)


def test_unknown_and_insufficient_capacity_are_not_readiness():
    assert preview(data())["reported_capacity"] == "unknown"
    out = preview(data(), available_bytes=1_000)
    assert out["reported_capacity"] == "reported_insufficient"
    assert out["status"] == "blocked_pending_explicit_approval"


def test_cancel_never_parses_request_or_performs_side_effects():
    assert preview(b"not valid", cancelled=True) == {
        "status": "cancelled", "side_effects": False,
    }


@pytest.mark.parametrize("bad", [
    b"", b"{}", b"[]", b"not json", b"\xff",
    b"x" * (MAX_BYTES + 1),
    b'{"schema_version":1,"schema_version":1}',
])
def test_bad_or_overlong_frame_fails_closed(bad):
    invalid(bad)


@pytest.mark.parametrize("changes", [
    {"schema_version": True},
    {"schema_version": 2},
    {"python_version": "3.13"},
    {"platform": "linux"},
    {"destination_kind": "../unsafe"},
    {"install": True},
    {"wheels": []},
    {"wheels": "not a list"},
    {"wheels": None},
])
def test_manifest_requires_exact_structure(changes):
    invalid(data(**changes))


@pytest.mark.parametrize("field,value", [
    ("package", "os"),
    ("package", "TORCH"),
    ("version", ">=2.6.0"),
    ("version", "2.6.0 && echo"),
    ("version", ""),
    ("filename", "../torch.whl"),
    ("filename", "C:\\secret\\torch.whl"),
    ("filename", "https://host/wheel.whl"),
    ("filename", "torch-2.6.0+cu124-py3-none-linux_x86_64.whl"),
    ("filename", "torch-2.6.0+cu124-cp311-cp311-any.whl\n"),
    ("filename", "torch-2.6.0+cu124-..-none-any.whl"),
    ("filename", "other-2.6.0+cu124-cp312-cp312-win_amd64.whl"),
    ("sha256", "not_a_sha256"),
    ("sha256", "F" * 64),
    ("declared_bytes", 0),
    ("declared_bytes", True),
    ("declared_bytes", 5 * 1024**3 + 1),
])
def test_bad_wheel_metadata_rejected_without_leaking_it(field, value):
    wheel = {**_SAMPLE["wheels"][0], field: value}
    invalid(data(wheels=[wheel]))


def test_no_duplicate_distributions():
    invalid(data(wheels=[_SAMPLE["wheels"][0], dict(_SAMPLE["wheels"][0])]))


def test_bounded_multi_package_preview():
    item = dict(_SAMPLE["wheels"][0])
    second = {
        "package": "pillow",
        "version": "11.2.0",
        "filename": "pillow-11.2.0-cp312-cp312-win_amd64.whl",
        "sha256": "b" * 64,
        "declared_bytes": 100_000,
    }
    result = preview(data(wheels=[item, second]))
    assert result["packages"] == ["pillow", "torch"]
    assert result["candidate_count"] == 2


@pytest.mark.parametrize("free", [-1, True, False, "12 GiB", 1.5, {}])
def test_capacity_is_not_implicitly_probed_or_coerced(free):
    with pytest.raises(PlanReject, match="^invalid_options$"):
        preview(data(), available_bytes=free)


def test_only_safe_metadata_operations_exist():
    # No URLs/paths accepted, runtime worker subprocess launched or GPU enabled.
    from app import create_app
    assert not any("install" in path or "worker" in path for path in create_app().openapi()["paths"])
    source = (Path(__file__).parent / "inference_install_preview.py").read_text(encoding="utf-8")
    for token in ("import subprocess", "import socket", "import requests", "import torch",
                  "import diffusers", "Popen(", "os.system(", "os.makedirs(", "open("):
        assert token not in source
