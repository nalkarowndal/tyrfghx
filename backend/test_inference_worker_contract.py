"""M4-1 CPU-only protocol specification regression and injection tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from inference_worker_contract import (
    MAX_FRAME_BYTES,
    ProtocolReject,
    describe_worker_contract,
    parse_describe_request,
)


def message(**overrides):
    data = {"protocol_version": 1, "operation": "describe", "request_id": "fixture_01"}
    data.update(overrides)
    return json.dumps(data).encode("utf-8")


def test_preview_metadata_remains_unconnected_and_gpu_free():
    result = json.loads(describe_worker_contract(message()))
    assert result == {
        "protocol_version": 1,
        "operation": "describe_result",
        "request_id": "fixture_01",
        "worker_state": "not_connected",
        "connection_ready": False,
        "launch_enabled": False,
        "supported_operations": ["describe"],
        "requires_native_parent_authentication": True,
        "requires_explicit_gpu_consent": True,
        "requires_isolated_python_environment": True,
        "cuda_tested": False,
        "models_opened": False,
        "downloads_performed": False,
        "packages_installed": False,
    }


@pytest.mark.parametrize("operation", [
    "run", "generate", "start", "launch", "install", "download", "delete",
    "probe_gpu", "execute", "open_model", "/api/generate", "describe; rm -rf /",
])
def test_rejects_any_execution_or_download_request(operation):
    with pytest.raises(ProtocolReject, match="^unsupported_operation$"):
        describe_worker_contract(message(operation=operation))


@pytest.mark.parametrize("frame,error", [
    (b"", "invalid_frame_size"),
    (b"x" * (MAX_FRAME_BYTES + 1), "invalid_frame_size"),
    (b"\xff", "invalid_json"),
    (b"{broken", "invalid_json"),
    (b"[]", "invalid_request_shape"),
    (b"true", "invalid_request_shape"),
    (b"{}", "invalid_request_shape"),
    (b'{"protocol_version":1,"operation":"describe","request_id":"fixture_01","extra":true}', "invalid_request_shape"),
    (b'{"protocol_version":1,"protocol_version":1,"operation":"describe","request_id":"fixture_01"}', "duplicate_json_key"),
    (b'{"protocol_version":true,"operation":"describe","request_id":"fixture_01"}', "unsupported_protocol_version"),
])
def test_invalid_frames_fail_closed(frame,error):
    with pytest.raises(ProtocolReject, match=f"^{error}$"):
        parse_describe_request(frame)


@pytest.mark.parametrize("version", [0, 2, True, False, "1", 1.0, None])
def test_protocol_version_is_exact_integer(version):
    with pytest.raises(ProtocolReject, match="^unsupported_protocol_version$"):
        parse_describe_request(message(protocol_version=version))


@pytest.mark.parametrize("request_id", [
    "short", "", "spaces are not allowed", "../model.safetensors",
    "secret=abc", "a" * 65, "한글id123456", 12345678, None,
])
def test_request_id_never_exposes_raw_paths_or_pii(request_id):
    with pytest.raises(ProtocolReject, match="^invalid_request_id$") as exc:
        parse_describe_request(message(request_id=request_id))
    assert str(request_id) not in str(exc.value)


def test_rejects_non_bytes_without_stringifying_or_logging():
    for frame in [None, {}, "secret path", bytearray(message()), memoryview(message())]:
        with pytest.raises(ProtocolReject, match="^invalid_frame_size$"):
            parse_describe_request(frame)


def test_contract_is_not_exposed_by_existing_packaged_api():
    from app import create_app
    paths = create_app().openapi()["paths"]
    assert "/api/status" in paths
    assert not any("worker" in key or "generate" in key for key in paths)
    assert describe_worker_contract(message()).startswith(b'{"protocol_version":1')


def test_contract_has_no_ai_imports_or_process_execution():
    source = (Path(__file__).parent / "inference_worker_contract.py").read_text(encoding="utf-8")
    # Check actual import statements, not natural-language docstrings.
    assert "import subprocess" not in source
    assert "import torch" not in source
    assert "import diffusers" not in source
    assert "import socket" not in source
    assert "import requests" not in source
    assert "os.system(" not in source
    assert "Popen(" not in source
