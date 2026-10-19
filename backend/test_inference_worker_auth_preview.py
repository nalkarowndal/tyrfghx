"""M4-1b: hostile-input and no-execution proof-contract tests (CPU only)."""
from __future__ import annotations

import hmac
import json
from pathlib import Path

import pytest

from inference_worker_auth_preview import (
    OneShotParentVerifier,
    ParentAuthReject,
)
from inference_worker_contract import MAX_FRAME_BYTES

_KEY = bytes(range(32))
_CHALLENGE = bytes(range(32, 64))
_REQUEST_ID = "parent_001"
_DOMAIN = b"aiimage-worker-parent-proof-v1\x00"


def proof_for(key=_KEY, challenge=_CHALLENGE, request_id=_REQUEST_ID):
    return hmac.digest(key, _DOMAIN + challenge + request_id.encode("ascii"), "sha256").hex()


def frame(**overrides):
    document = {
        "protocol_version": 1,
        "operation": "parent_proof",
        "request_id": _REQUEST_ID,
        "proof": proof_for(),
    }
    document.update(overrides)
    return json.dumps(document, ensure_ascii=True).encode("utf-8")


def reject(frame_bytes, code="authentication_failed", *, key=_KEY, challenge=_CHALLENGE):
    verifier = OneShotParentVerifier(key, challenge)
    with pytest.raises(ParentAuthReject) as exc:
        verifier.verify(frame_bytes)
    assert str(exc.value) == code
    with pytest.raises(ParentAuthReject, match="^authentication_consumed$"):
        verifier.verify(frame())
    return str(exc.value)


def test_correct_parent_proof_is_one_shot_without_starting_worker():
    verifier = OneShotParentVerifier(_KEY, _CHALLENGE)
    assert verifier.verify(frame()) is True
    with pytest.raises(ParentAuthReject, match="^authentication_consumed$"):
        verifier.verify(frame())


def test_replay_of_old_proof_fails_after_challenge_rotation():
    other_challenge = bytes(reversed(_CHALLENGE))
    reject(frame(), challenge=other_challenge)
    other_key = bytes(reversed(_KEY))
    reject(frame(), key=other_key)
    assert OneShotParentVerifier(_KEY, _CHALLENGE).verify(frame()) is True


def test_proof_is_bound_to_request_id():
    reject(frame(request_id="parent_002"))
    changed_id = "parent_002"
    assert OneShotParentVerifier(_KEY, _CHALLENGE).verify(
        frame(request_id=changed_id, proof=proof_for(request_id=changed_id))
    ) is True


@pytest.mark.parametrize("invalid", [
    b"",
    b"not json",
    b"\xff",
    b"[]" ,
    b"{}",
    b" " * (MAX_FRAME_BYTES + 1),
    b'{"protocol_version":1,"protocol_version":1,"operation":"parent_proof","request_id":"parent_001","proof":"00"}',
])
def test_bad_json_and_duplicate_keys_consume_attempt(invalid):
    reject(invalid)


@pytest.mark.parametrize("overrides", [
    {"protocol_version": 2},
    {"protocol_version": True},
    {"protocol_version": "1"},
    {"operation": "describe"},
    {"operation": "execute"},
    {"operation": "launch"},
    {"operation": "gpu_probe"},
    {"operation": None},
    {"request_id": "../secret-path"},
    {"request_id": "tiny"},
    {"request_id": 12345678},
    {"request_id": "한글_auth_001"},
    {"proof": "0" * 63},
    {"proof": "A" * 64},
    {"proof": "0" * 64 + "../"},
    {"proof": None},
    {"extra": "C:/private/model"},
])
def test_invalid_shapes_and_operations_fail_closed(overrides):
    reject(frame(**overrides))


def test_bad_proof_never_echoes_sensitive_data():
    secret = "x" * 64
    error = reject(frame(proof=secret))
    assert error == "authentication_failed"
    assert secret not in error
    assert _KEY.hex() not in error
    assert _CHALLENGE.hex() not in error


@pytest.mark.parametrize("bad_key,bad_challenge", [
    (b"", _CHALLENGE),
    (b"a" * 31, _CHALLENGE),
    (b"a" * 33, _CHALLENGE),
    ("secret", _CHALLENGE),
    (_KEY, b""),
    (_KEY, b"n" * 31),
    (_KEY, bytearray(_CHALLENGE)),
])
def test_requires_exact_binary_material_without_logging(bad_key, bad_challenge):
    with pytest.raises(ParentAuthReject, match="^invalid_auth_material$"):
        OneShotParentVerifier(bad_key, bad_challenge)


def test_no_worker_api_launch_or_runtime_dependencies_added():
    from app import create_app
    routes = create_app().openapi()["paths"]
    assert "/api/status" in routes
    assert not any("worker" in path or "generate" in path for path in routes)
    source = (Path(__file__).parent / "inference_worker_auth_preview.py").read_text(encoding="utf-8")
    for banned in ("import torch", "import diffusers", "import socket", "import subprocess",
                   "Popen(", "os.system(", "pip install", "requests.get(", "create_subprocess"):
        assert banned not in source
