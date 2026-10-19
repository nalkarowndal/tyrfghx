"""M4-1b: offline, one-shot proof of a future native parent (NO IPC transport).

This is a pure stdlib contract helper, not an authentication service.
The parent must independently create a fresh 32-byte session key and a
fresh 32-byte challenge using an OS CSPRNG, then securely provide them to
an owned worker through a private bootstrap channel. That native channel,
process ownership and authorization are NOT implemented here.

No worker launch, API registration, GPU probe, model read or package install.
"""
from __future__ import annotations

import hmac
import json
import re

from inference_worker_contract import MAX_FRAME_BYTES, PROTOCOL_VERSION, ProtocolReject

_AUTH_KEYS = frozenset({"protocol_version", "operation", "request_id", "proof"})
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_PROOF = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = b"aiimage-worker-parent-proof-v1\x00"


class ParentAuthReject(ProtocolReject):
    """Fixed error code: never disclose frame, key, challenge or proof."""


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ParentAuthReject("authentication_failed")
        obj[key] = value
    return obj


def _parse_parent_proof(frame: bytes) -> tuple[str, bytes]:
    if type(frame) is not bytes or not frame or len(frame) > MAX_FRAME_BYTES:
        raise ParentAuthReject("authentication_failed")
    try:
        document = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_keys)
    except ParentAuthReject:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ParentAuthReject("authentication_failed") from None
    if type(document) is not dict or frozenset(document) != _AUTH_KEYS:
        raise ParentAuthReject("authentication_failed")
    if type(document["protocol_version"]) is not int or document["protocol_version"] != PROTOCOL_VERSION:
        raise ParentAuthReject("authentication_failed")
    if type(document["operation"]) is not str or document["operation"] != "parent_proof":
        raise ParentAuthReject("authentication_failed")
    request_id = document["request_id"]
    proof = document["proof"]
    if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
        raise ParentAuthReject("authentication_failed")
    if type(proof) is not str or _PROOF.fullmatch(proof) is None:
        raise ParentAuthReject("authentication_failed")
    return request_id, bytes.fromhex(proof)


class OneShotParentVerifier:
    """Check one HMAC-SHA256 proof bound to a parent-owned session challenge.

    Consumes its only attempt even on malformed frames or wrong credentials.
    A successful return proves knowledge of the supplied secret in-process;
    it does NOT certify a native peer, open an IPC channel or enable execution.
    """

    __slots__ = ("_key", "_challenge", "_consumed")

    def __init__(self, key: bytes, challenge: bytes) -> None:
        if type(key) is not bytes or len(key) != 32:
            raise ParentAuthReject("invalid_auth_material")
        if type(challenge) is not bytes or len(challenge) != 32:
            raise ParentAuthReject("invalid_auth_material")
        self._key = key
        self._challenge = challenge
        self._consumed = False

    def verify(self, frame: bytes) -> bool:
        if self._consumed:
            raise ParentAuthReject("authentication_consumed")
        self._consumed = True
        request_id, supplied = _parse_parent_proof(frame)
        message = _DOMAIN + self._challenge + request_id.encode("ascii")
        expected = hmac.digest(self._key, message, "sha256")
        if not hmac.compare_digest(expected, supplied):
            raise ParentAuthReject("authentication_failed")
        return True
