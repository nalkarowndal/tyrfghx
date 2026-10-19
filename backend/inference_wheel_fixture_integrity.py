"""M4-1e: read-only integrity QA for tiny, synthetic wheel-named test files.

Not production wheel verification. The caller must supply an isolated
fixture directory with a marker and mock bytes, NEVER a real user model
or package cache. No network, package import, install, extraction, GPU
probe, or Tauri/FastAPI route uses this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import stat

from inference_install_preview import PlanReject, preview

FIXTURE_MARKER = ".aiimage-m4-1e-synthetic-fixture"
MARKER_BYTES = b"aiimage:m4-1e:synthetic-qa-only:v1\n"
MAX_FIXTURE_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _has_reparse(status: os.stat_result) -> bool:
    return bool(getattr(status, "st_file_attributes", 0) & _REPARSE_POINT)


def _safe_fixture_root(root: Path) -> Path:
    if type(root) is not Path or not root.is_absolute():
        raise ValueError("invalid_fixture")
    status = os.lstat(root)
    if not stat.S_ISDIR(status.st_mode) or _has_reparse(status):
        raise ValueError("invalid_fixture")
    resolved = root.resolve(strict=True)
    if resolved != root.absolute():
        raise ValueError("invalid_fixture")
    marker = root / FIXTURE_MARKER
    info = os.lstat(marker)
    if not stat.S_ISREG(info.st_mode) or _has_reparse(info) or info.st_size != len(MARKER_BYTES):
        raise ValueError("invalid_fixture")
    # Marker is an explicit QA-only guard, not a production access-control token.
    if marker.read_bytes() != MARKER_BYTES:
        raise ValueError("invalid_fixture")
    return resolved


def _inspect_mock_file(root: Path, filename: str, expected_size: int, expected_hex: str) -> bool:
    if expected_size > MAX_FIXTURE_BYTES:
        return False
    path = root / filename
    try:
        before = os.lstat(path)
        if (not stat.S_ISREG(before.st_mode) or _has_reparse(before)
            or before.st_size != expected_size or before.st_nlink != 1):
            return False
        if path.resolve(strict=True).parent != root:
            return False
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            initial = os.fstat(stream.fileno())
            if (not stat.S_ISREG(initial.st_mode) or _has_reparse(initial)
                or (initial.st_dev, initial.st_ino, initial.st_size) !=
                   (before.st_dev, before.st_ino, before.st_size)):
                return False
            digest = hashlib.sha256()
            received = 0
            while True:
                block = stream.read(min(CHUNK_BYTES, expected_size - received + 1))
                if not block:
                    break
                received += len(block)
                if received > expected_size:
                    return False
                digest.update(block)
            final = os.fstat(stream.fileno())
            if (received != expected_size
                or (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)
                   != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)):
                return False
            return hmac.compare_digest(digest.digest(), bytes.fromhex(expected_hex))
    except (OSError, ValueError):
        # Always fail closed with no filesystem path or private bytes in output.
        return False


def verify_synthetic_fixture(frame: bytes, root: Path, *, cancelled: bool = False) -> dict:
    """Read only explicitly marked QA fixtures, never user-selected real files.

    A success means synthetic *bytes* matched the supplied digest. It does
    NOT imply trusted source provenance, wheel format/tag compatibility,
    native Windows race-free path handling, or permission to install.
    """
    if type(cancelled) is not bool:
        raise PlanReject("invalid_options")
    if cancelled:
        return {"status": "cancelled", "side_effects_performed": False}
    # Reuse strict duplicate-key, schema, filename and SHA256 syntax checks.
    preview(frame)
    result = {
        "status": "synthetic_fixture_rejected",
        "synthetic_fixture": True,
        "checked_count": 0,
        "all_fixture_hashes_match": False,
        "wheel_archive_validated": False,
        "wheel_compatibility_verified": False,
        "source_provenance_verified": False,
        "production_path_safe": False,
        "user_files_touched": False,
        "downloads_performed": False,
        "packages_installed": False,
        "gpu_accessed": False,
        "execution_enabled": False,
    }
    try:
        trusted_root = _safe_fixture_root(root)
        # Validated by preview, including duplicate keys; this decode
        # only extracts already-validated fixed schema fields.
        wheels = json.loads(frame)["wheels"]
        result["checked_count"] = len(wheels)
        if all(_inspect_mock_file(trusted_root, wheel["filename"],
                                  wheel["declared_bytes"], wheel["sha256"])
               for wheel in wheels):
            result["status"] = "synthetic_fixture_verified"
            result["all_fixture_hashes_match"] = True
    except (OSError, ValueError, TypeError, RuntimeError):
        pass
    return result
