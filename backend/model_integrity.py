"""Local integrity manifest. Snapshots are NOT live cryptographic attestations."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from model_metadata import valid_id
from model_manifest_lock import exclusive_manifest_write

CHUNK_SIZE = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 1_048_576
HASH_RE = re.compile(r"^[a-f0-9]{64}$")


class IntegrityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    mtime_ns: int = Field(ge=0)


IntegrityState = Literal["not_recorded", "snapshot_unchanged", "file_changed"]


def read_manifest(root: Path, *, strict: bool = False) -> dict[str, IntegrityEntry]:
    """Reject corrupt/oversized/symlinked manifests on writes; fail closed for scans."""
    file = root / "integrity.json"
    try:
        if root.is_symlink() or file.is_symlink():
            raise ValueError("Unsafe integrity manifest path")
        if not file.exists():
            return {}
        if file.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("Integrity manifest exceeds limit")
        data = json.loads(file.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("models"), dict)
                or len(data["models"]) > 3000):
            raise ValueError("Invalid integrity manifest")
        entries: dict[str, IntegrityEntry] = {}
        for key, value in data["models"].items():
            if not isinstance(key, str) or not valid_id(key):
                raise ValueError("Invalid model ID in integrity manifest")
            entries[key] = IntegrityEntry.model_validate(value)
        return entries
    except (OSError, ValueError, UnicodeError, ValidationError) as exc:
        if strict:
            raise ValueError("Integrity manifest is unsafe or damaged; backup and repair it first") from exc
        return {}


def save_manifest_entry(root: Path, model_id: str, entry: IntegrityEntry) -> None:
    if not valid_id(model_id) or root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid model root/identifier")
    manifest = root / "integrity.json"
    # The Rust desktop importer uses the very same cooperative lock.
    with exclusive_manifest_write(root):
        if manifest.is_symlink():
            raise ValueError("Manifest symlinks are forbidden")
        entries = read_manifest(root, strict=True)
        entries[model_id] = entry
        data = json.dumps(
            {"schema_version": 1, "models": {k: v.model_dump() for k, v in entries.items()}},
            sort_keys=True, indent=2,
        )
        if len(data.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise ValueError("Integrity manifest would exceed size limit")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=root, prefix=".integrity-", suffix=".tmp",
                delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                temp.write(data)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_path, manifest)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

def model_file(root: Path, model_id: str) -> Path:
    if not valid_id(model_id) or root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid model ID/root")
    folder_name, name = model_id.split("/")
    folder = root / folder_name
    file = folder / name
    if folder.is_symlink() or not folder.is_dir() or file.is_symlink() or not file.is_file():
        raise ValueError("Model file must exist in a real approved directory")
    return file


def hash_model(path: Path) -> str:
    """Stream from disk, bounded RAM, without torch/pickle/model loading."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("Cannot hash nonregular or symlinked file")
    digest = hashlib.sha256()
    with path.open("rb") as src:
        while chunk := src.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(root: Path, model_id: str) -> tuple[str, str]:
    """Compute CURRENT checksum against recorded hash; never updates the record."""
    file = model_file(root, model_id)
    manifest = read_manifest(root, strict=True)
    digest = hash_model(file)
    stored = manifest.get(model_id)
    if stored is None:
        return "unrecorded", digest
    if hmac.compare_digest(digest, stored.sha256):
        return "match", digest
    return "mismatch", digest


def integrity_state(path: Path, entry: IntegrityEntry | None) -> IntegrityState:
    if entry is None:
        return "not_recorded"
    try:
        stat = path.stat()
        if stat.st_size == entry.size_bytes and stat.st_mtime_ns == entry.mtime_ns:
            return "snapshot_unchanged"
    except OSError:
        pass
    return "file_changed"
