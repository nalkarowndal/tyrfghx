"""M4-1: *in-process only* prototype of a future inference-worker protocol.

NOT a network endpoint, subprocess, Tauri command, GPU probe or executor.
The only accepted operation is the safe, constant metadata "describe".
The module never installs packages, imports AI frameworks, or reads model files.

Future transport MUST provide its own native-parent authentication, bounded
framing, Windows Job Object lifecycle and separate user GPU consent.
"""
from __future__ import annotations

import json
import re

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 4096
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_REQUEST_KEYS = frozenset({"protocol_version", "operation", "request_id"})


class ProtocolReject(ValueError):
    """Stable public error with no paths, tokens, request text, or secrets."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolReject("duplicate_json_key")
        result[key] = value
    return result


def parse_describe_request(frame: bytes) -> dict:
    """Parse a strict metadata-only frame; reject unsupported operations.

    This validates only syntax and the no-execution contract. It intentionally
    does NOT confer authentication or readiness to execute a worker.
    """
    if type(frame) is not bytes or not frame or len(frame) > MAX_FRAME_BYTES:
        raise ProtocolReject("invalid_frame_size")
    try:
        body = json.loads(frame.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except ProtocolReject:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ProtocolReject("invalid_json") from None
    if type(body) is not dict or frozenset(body) != _REQUEST_KEYS:
        raise ProtocolReject("invalid_request_shape")
    if type(body["protocol_version"]) is not int or body["protocol_version"] != PROTOCOL_VERSION:
        raise ProtocolReject("unsupported_protocol_version")
    if body["operation"] != "describe" or type(body["operation"]) is not str:
        raise ProtocolReject("unsupported_operation")
    if type(body["request_id"]) is not str or _REQUEST_ID.fullmatch(body["request_id"]) is None:
        raise ProtocolReject("invalid_request_id")
    return body


def describe_worker_contract(frame: bytes) -> bytes:
    """Build a fixed offline contract response; no real worker is started.

    The sanitized request id is the only caller-controlled field echoed.
    No user-controlled paths, commands, model names or tokens are accepted.
    """
    request = parse_describe_request(frame)
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "operation": "describe_result",
        "request_id": request["request_id"],
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
    result = json.dumps(response, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(result) > MAX_FRAME_BYTES:
        raise ProtocolReject("response_frame_too_large")
    return result
