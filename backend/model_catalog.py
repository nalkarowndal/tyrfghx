"""Read-only local model inventory. Never deserialize model weights during scanning."""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from model_integrity import IntegrityState, read_manifest, integrity_state
from model_metadata import ModelFamily, infer_family, read_annotations

MODEL_ROOT = Path(__file__).resolve().parent.parent / "models"
MODEL_FOLDERS = {"checkpoints": "checkpoint", "loras": "lora", "vae": "vae"}
MAX_HEADER_BYTES = 1_048_576
MAX_MODELS_PER_CATEGORY = 3_000


class ModelRecord(BaseModel):
    id: str
    name: str
    category: Literal["checkpoint", "lora", "vae"]
    file_format: Literal["safetensors", "ckpt"]
    size_bytes: int
    reported_architecture: str | None = None
    validation: Literal["metadata_only", "invalid_header", "blocked_legacy"]
    note: str
    display_name: str | None = None
    family: ModelFamily | None = None
    family_source: Literal["header", "manual", "unknown"] = "unknown"
    license: str | None = None
    notes: str | None = None
    integrity_state: IntegrityState = "not_recorded"
    recorded_sha256: str | None = None
    potential_duplicate_ids: list[str] = Field(default_factory=list)


def _read_safetensors_architecture(path: Path, size: int) -> tuple[str | None, bool]:
    """Parse only bounded JSON header bytes; do not import torch or load tensors."""
    try:
        if size < 10:
            return None, False
        with path.open("rb") as file:
            first = file.read(8)
            if len(first) != 8:
                return None, False
            header_len = struct.unpack("<Q", first)[0]
            if not 2 <= header_len <= min(MAX_HEADER_BYTES, size - 8):
                return None, False
            header = json.loads(file.read(header_len))
        if not isinstance(header, dict):
            return None, False
        metadata = header.get("__metadata__", {})
        if not isinstance(metadata, dict):
            return None, False
        for key in ("modelspec.architecture", "ss_base_model_version"):
            value = metadata.get(key)
            if isinstance(value, str) and 0 < len(value) <= 128:
                return value, True
        return None, True
    except (OSError, ValueError, UnicodeError, struct.error, MemoryError):
        return None, False


def scan_models(root: Path = MODEL_ROOT) -> list[ModelRecord]:
    """Only scan direct model files in predefined category directories.

    Symlinks are ignored. Model files are never executed, deserialized, or opened
    with unsafe pickle/torch loaders. Architecture metadata is unverified.
    """
    if root.is_symlink() or not root.is_dir():
        return []
    results: list[ModelRecord] = []
    annotations = read_annotations(root)
    integrity = read_manifest(root)
    for dirname, category in MODEL_FOLDERS.items():
        folder = root / dirname
        if folder.is_symlink() or not folder.is_dir():
            continue
        try:
            entries = sorted(folder.iterdir(), key=lambda x: x.name.casefold())
        except OSError:
            continue
        for path in entries[:MAX_MODELS_PER_CATEGORY]:
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                ext = path.suffix.casefold()
                if ext not in (".safetensors", ".ckpt"):
                    continue
                size = path.stat().st_size
                if ext == ".ckpt":
                    results.append(ModelRecord(
                        id=f"{dirname}/{path.name}", name=path.name, category=category,
                        file_format="ckpt", size_bytes=size,
                        validation="blocked_legacy",
                        note="CKPT는 역직렬화 위험이 있어 자동 로딩이 차단됩니다.",
                    ))
                    continue
                architecture, valid = _read_safetensors_architecture(path, size)
                results.append(ModelRecord(
                    id=f"{dirname}/{path.name}", name=path.name, category=category,
                    file_format="safetensors", size_bytes=size,
                    reported_architecture=architecture,
                    validation="metadata_only" if valid else "invalid_header",
                    note=("헤더만 확인됨. 모델 호환성 및 실행 여부는 미검증입니다."
                          if valid else "safetensors 헤더를 읽을 수 없습니다. 파일 검증이 필요합니다."),
                ))
            except OSError:
                continue
    for item in results:
        # Display metadata never changes model weights or bypasses validation.
        if item.file_format != "safetensors":
            continue
        record = integrity.get(item.id)
        item.integrity_state = integrity_state(root / item.id, record)
        if record is not None:
            item.recorded_sha256 = record.sha256
        annotation = annotations.get(item.id)
        if annotation:
            item.display_name = annotation.display_name
            item.license = annotation.license
            item.notes = annotation.notes
        reported_family = infer_family(item.reported_architecture)
        if annotation and annotation.family_override:
            item.family = annotation.family_override
            item.family_source = "manual"
        elif reported_family:
            item.family = reported_family
            item.family_source = "header"
    # Identical recorded hashes are only duplicate hints, not a live verification.
    for item in results:
        if item.integrity_state == "snapshot_unchanged" and item.recorded_sha256:
            item.potential_duplicate_ids = [
                other.id for other in results
                if other.id != item.id
                and other.integrity_state == "snapshot_unchanged"
                and other.recorded_sha256 == item.recorded_sha256
            ]
    return results
