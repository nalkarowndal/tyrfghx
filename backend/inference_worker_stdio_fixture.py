"""M4-1c: *test-only* CPU worker for native owned-pipe QA.

NEVER register as a FastAPI endpoint, Tauri command or installable sidecar.
All session material is synthetic test data, read once from a private pipe.
No CUDA, model access, download, package installation or network.
"""
from __future__ import annotations

import hmac
import json
import re
import sys
import time
from pathlib import Path

# -I removes script paths from Python's implicit sys.path. Fixture-local import
# is explicit and fixed to the repository's checked-in backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inference_worker_contract import MAX_FRAME_BYTES, describe_worker_contract, ProtocolReject  # noqa: E402

_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_HEX32 = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = b"aiimage-worker-parent-proof-v1\x00"
_BOOTSTRAP_KEYS = frozenset({"protocol_version", "operation", "request_id", "session_key", "challenge"})


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_bootstrap")
        result[key] = value
    return result


def bounded_read():
    # Read at most MAX_FRAME_BYTES+1 to detect truncated/oversized input.
    line = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
    if not line or len(line) > MAX_FRAME_BYTES or not line.endswith(b"\n"):
        raise ValueError("invalid_frame")
    return line


def read_bootstrap():
    payload = json.loads(bounded_read().decode("utf-8"), object_pairs_hook=_unique_pairs)
    if type(payload) is not dict or frozenset(payload) != _BOOTSTRAP_KEYS:
        raise ValueError("invalid_bootstrap")
    if type(payload["protocol_version"]) is not int or payload["protocol_version"] != 1:
        raise ValueError("invalid_bootstrap")
    if type(payload["operation"]) is not str or payload["operation"] != "bootstrap":
        raise ValueError("invalid_bootstrap")
    request_id = payload["request_id"]
    key_hex = payload["session_key"]
    challenge_hex = payload["challenge"]
    if type(request_id) is not str or not _REQUEST_ID.fullmatch(request_id):
        raise ValueError("invalid_bootstrap")
    for value in (key_hex, challenge_hex):
        if type(value) is not str or not _HEX32.fullmatch(value):
            raise ValueError("invalid_bootstrap")
    return request_id, bytes.fromhex(key_hex), bytes.fromhex(challenge_hex)


def write_frame(data):
    frame = json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError("invalid_frame")
    sys.stdout.buffer.write(frame)
    sys.stdout.buffer.flush()


def main():
    # Mode argument is a fixed test-only fault selector, never a secret or path.
    if len(sys.argv) != 2 or sys.argv[1] not in {"success", "tamper", "oversize", "stall", "crash"}:
        return 2
    mode = sys.argv[1]
    try:
        request_id, key, challenge = read_bootstrap()
        if mode == "stall":
            time.sleep(20)
            return 3
        if mode == "crash":
            return 4
        if mode == "oversize":
            sys.stdout.buffer.write(b"x" * (MAX_FRAME_BYTES + 1) + b"\n")
            sys.stdout.buffer.flush()
            return 5
        proof = hmac.digest(key, _DOMAIN + challenge + request_id.encode("ascii"), "sha256").hex()
        if mode == "tamper":
            proof = "0" * 64 if proof != "0" * 64 else "f" * 64
        write_frame({"protocol_version": 1, "operation": "parent_proof",
                     "request_id": request_id, "proof": proof})
        # A valid proof alone never enables GPU, generation or arbitrary IPC.
        if mode != "success":
            return 6
        request = bounded_read()
        result = describe_worker_contract(request.strip(b"\n"))
        sys.stdout.buffer.write(result + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except (UnicodeError, ValueError, TypeError, RecursionError, OSError, ProtocolReject):
        # No secrets, request content, exception strings or local paths in logs.
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
