"""M4-1f: bounded in-memory *synthetic* wheel-structure QA (NO install).

This module receives bytes from test fixtures, never a path, downloader, Python
runtime, GPU process, user model or wheel cache. A successful result does NOT
establish real-wheel trust, signature, provenance or installer compatibility.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import stat
import zipfile

MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 32
MAX_ENTRY_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024

_NAME = re.compile(
    r"(torch|diffusers|transformers|accelerate|safetensors|pillow)-"
    r"([0-9]+(?:\.[0-9]+){1,3}(?:\+(?:cpu|cu[0-9]{3,4}))?)-"
    r"(cp312-cp312-win_amd64|py3-none-any)\.whl\Z"
)


class SyntheticWheelReject(ValueError):
    """No source bytes, file paths, command strings or private data in errors."""


def _reject() -> None:
    raise SyntheticWheelReject("synthetic_archive_rejected")


def _archive_path(name: str) -> bool:
    if not isinstance(name, str) or not 1 <= len(name) <= 220:
        return False
    if name.startswith(("/", ".")) or "\\" in name or ":" in name or "\x00" in name:
        return False
    if any(c in name for c in ("\r", "\n", "\t")):
        return False
    if re.fullmatch(r"[A-Za-z0-9_+./-]+", name) is None:
        return False
    segments = name.split("/")
    reserved = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{index}" for prefix in ("com", "lpt") for index in range(1, 10)
    }
    return all(
        p not in ("", ".", "..") and not p.endswith((" ", "."))
        and p.split(".", 1)[0].casefold() not in reserved
        for p in segments
    )


def _record_digest(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")


def _required_line(payload: bytes, label: str, value: str) -> bool:
    if len(payload) > MAX_RECORD_BYTES:
        return False
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        return False
    fields = [line.partition(": ")[2] for line in text.splitlines()
              if line.startswith(label + ": ")]
    return fields == [value]


def _check_record(raw: bytes, extracted: dict[str, bytes], record_name: str) -> bool:
    if len(raw) > MAX_RECORD_BYTES:
        return False
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""))
        seen = set()
        for row in rows:
            if len(row) != 3:
                return False
            name, digest, length = row
            if name not in extracted or name in seen:
                return False
            seen.add(name)
            if name == record_name:
                if digest or length:
                    return False
            else:
                if digest != "sha256=" + _record_digest(extracted[name]):
                    return False
                if length != str(len(extracted[name])):
                    return False
        return seen == set(extracted)
    except (UnicodeError, ValueError, csv.Error):
        return False


def inspect_synthetic_wheel(archive_bytes: bytes, filename: str, *,
                            cancelled: bool = False) -> dict:
    """Inspect a tiny in-memory archive only; never extract or execute."""
    if type(cancelled) is not bool:
        raise SyntheticWheelReject("invalid_preview_options")
    if cancelled:
        return {"status": "cancelled", "side_effects_performed": False}
    if (type(archive_bytes) is not bytes or not archive_bytes
            or len(archive_bytes) > MAX_ARCHIVE_BYTES
            or type(filename) is not str):
        _reject()
    match = _NAME.fullmatch(filename)
    if match is None:
        _reject()
    distribution, version, wheel_tag = match.groups()
    prefix = distribution + "-" + version + ".dist-info/"
    wheel_name, metadata_name, record_name = (
        prefix + "WHEEL", prefix + "METADATA", prefix + "RECORD"
    )
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            infos = archive.infolist()
            if not 3 <= len(infos) <= MAX_ENTRIES or archive.comment:
                _reject()
            extracted: dict[str, bytes] = {}
            normalized_names: set[str] = set()
            declared_total = 0
            for info in infos:
                name = info.filename
                if (name.casefold() in normalized_names
                        or not _archive_path(name) or info.is_dir()):
                    _reject()
                normalized_names.add(name.casefold())
                if info.flag_bits & (0x01 | 0x08) or info.compress_type not in (
                        zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    _reject()
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG):
                    _reject()
                if info.file_size > MAX_ENTRY_BYTES or info.file_size < 0:
                    _reject()
                declared_total += info.file_size
                if declared_total > MAX_UNCOMPRESSED_BYTES:
                    _reject()
                # Prevent tiny compressed bytes from advertising huge output.
                if info.file_size > 4096 and info.file_size > 100 * max(info.compress_size, 1):
                    _reject()
                content = archive.read(info)
                if len(content) != info.file_size:
                    _reject()
                extracted[name] = content
            if not all(key in extracted for key in (wheel_name, metadata_name, record_name)):
                _reject()
            if not _required_line(extracted[wheel_name], "Wheel-Version", "1.0"):
                _reject()
            if not (_required_line(extracted[wheel_name], "Root-Is-Purelib", "true")
                    or _required_line(extracted[wheel_name], "Root-Is-Purelib", "false")):
                _reject()
            if not _required_line(extracted[wheel_name], "Tag", wheel_tag):
                _reject()
            if not _required_line(extracted[metadata_name], "Metadata-Version", "2.1"):
                _reject()
            if not _required_line(extracted[metadata_name], "Name", distribution):
                _reject()
            if not _required_line(extracted[metadata_name], "Version", version):
                _reject()
            if not _check_record(extracted[record_name], extracted, record_name):
                _reject()
            return {
                "status": "synthetic_archive_structure_verified",
                "synthetic_fixture": True,
                "checked_entries": len(infos),
                "record_hashes_match": True,
                "sample_target_tag_matched": True,
                "production_wheel_compatible": False,
                "archive_parser_ambiguity_excluded": False,
                "source_provenance_verified": False,
                "signature_verified": False,
                "production_install_authorized": False,
                "downloads_performed": False,
                "packages_installed": False,
                "gpu_accessed": False,
            }
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, UnicodeError,
            ValueError, RuntimeError, EOFError):
        _reject()
    _reject()
