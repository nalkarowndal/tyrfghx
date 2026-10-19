"""Offline-only AI wheel manifest preview. No package installation or IO."""
from __future__ import annotations

import json
import re

PACKAGES = frozenset(("torch", "diffusers", "transformers", "accelerate", "safetensors", "pillow"))
MAX_BYTES = 32768
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:\+(?:cpu|cu[0-9]{3,4}))?\Z")


class PlanReject(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanReject("invalid_manifest")
        result[key] = value
    return result


def _decode(frame):
    if type(frame) is not bytes or not frame or len(frame) > MAX_BYTES:
        raise PlanReject("invalid_manifest")
    try:
        return json.loads(frame.decode("utf-8"), object_pairs_hook=_pairs)
    except PlanReject:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise PlanReject("invalid_manifest") from None


def preview(frame: bytes, *, available_bytes: int | None = None, cancelled: bool = False) -> dict:
    """Data-only estimate; declared wheel sizes and storage values are unverified."""
    if type(cancelled) is not bool:
        raise PlanReject("invalid_options")
    if cancelled:
        return {"status": "cancelled", "side_effects": False}
    if available_bytes is not None and (type(available_bytes) is not int or available_bytes < 0):
        raise PlanReject("invalid_options")
    data = _decode(frame)
    if type(data) is not dict or set(data) != {"schema_version", "platform", "python_version", "destination_kind", "wheels"}:
        raise PlanReject("invalid_manifest")
    if (type(data["schema_version"]) is not int or data["schema_version"] != 1
        or data["platform"] != "windows_x86_64" or type(data["platform"]) is not str
        or data["python_version"] != "3.12" or type(data["python_version"]) is not str
        or data["destination_kind"] != "user_selected_private_venv"
        or type(data["destination_kind"]) is not str):
        raise PlanReject("invalid_manifest")
    wheels = data["wheels"]
    if type(wheels) is not list or not 1 <= len(wheels) <= 6:
        raise PlanReject("invalid_manifest")
    names = set()
    total = 0
    for item in wheels:
        if type(item) is not dict or set(item) != {"package", "version", "filename", "sha256", "declared_bytes"}:
            raise PlanReject("invalid_manifest")
        name, version, filename, digest, size = (item[k] for k in ("package", "version", "filename", "sha256", "declared_bytes"))
        if type(name) is not str or name not in PACKAGES or name in names:
            raise PlanReject("invalid_manifest")
        names.add(name)
        if type(version) is not str or not VERSION.fullmatch(version):
            raise PlanReject("invalid_manifest")
        if type(filename) is not str or not 12 <= len(filename) <= 200:
            raise PlanReject("invalid_manifest")
        if ".." in filename or any(c in filename for c in ("/", "\\", ":", "%", " ")):
            raise PlanReject("invalid_manifest")
        parts = filename.removesuffix(".whl").split("-")
        if not filename.endswith(".whl") or len(parts) not in (5, 6) or parts[0] != name or parts[1] != version:
            raise PlanReject("invalid_manifest")
        if not all(re.fullmatch(r"[A-Za-z0-9_.+]+", part) for part in parts) or parts[-1] not in ("any", "win_amd64"):
            raise PlanReject("invalid_manifest")
        if type(digest) is not str or not SHA256.fullmatch(digest):
            raise PlanReject("invalid_manifest")
        if type(size) is not int or not 0 < size <= 5 * 1024**3:
            raise PlanReject("invalid_manifest")
        total += size
        if total > 20 * 1024**3:
            raise PlanReject("invalid_manifest")
    estimate = 3 * total + 2 * 1024**3
    status = ("unknown" if available_bytes is None else
              "reported_insufficient" if available_bytes < estimate else "reported_sufficient_unverified")
    return {
        "schema_version": 1,
        "status": "blocked_pending_explicit_approval",
        "packages": sorted(names),
        "candidate_count": len(names),
        "declared_archive_bytes": total,
        "provisional_storage_estimate_bytes": estimate,
        "reported_capacity": status,
        "estimate_is_verified": False,
        "source_provenance_verified": False,
        "hashes_verified": False,
        "wheel_compatibility_verified": False,
        "dependencies_verified": False,
        "target_path_verified": False,
        "runtime_verified": False,
        "user_approval_granted": False,
        "files_opened": False,
        "downloads_performed": False,
        "packages_installed": False,
        "gpu_accessed": False,
        "execution_enabled": False,
    }
