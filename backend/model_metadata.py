"""Bounded local-only metadata annotations; never deserialize or import model weights."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ModelFamily = Literal["sd15", "sd2", "sdxl", "sd3", "flux"]
FOLDERS = ("checkpoints", "loras", "vae")
MAX_ANNOTATIONS_BYTES = 1_048_576


class ModelAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=96)
    family_override: ModelFamily | None = None
    license: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=400)


def valid_id(model_id: str) -> bool:
    parts = model_id.split("/")
    return (
        len(parts) == 2 and parts[0] in FOLDERS
        and parts[1] not in ("", ".", "..")
        and "\\" not in parts[1] and ":" not in parts[1]
        and parts[1].casefold().endswith(".safetensors")
    )


def read_annotations(root: Path) -> dict[str, ModelAnnotation]:
    registry = root / "annotations.json"
    try:
        if root.is_symlink() or registry.is_symlink() or registry.stat().st_size > MAX_ANNOTATIONS_BYTES:
            return {}
        data = json.loads(registry.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("models"), dict)
                or len(data["models"]) > 3000):
            return {}
    except (OSError, ValueError, UnicodeError):
        return {}
    results = {}
    for model_id, value in data["models"].items():
        if not isinstance(model_id, str) or not valid_id(model_id):
            continue
        try:
            results[model_id] = ModelAnnotation.model_validate(value)
        except ValidationError:
            continue
    return results


def save_annotation(root: Path, model_id: str, annotation: ModelAnnotation) -> None:
    """CLI-only mutation. No HTTP write endpoint; cannot register outside model root."""
    if not valid_id(model_id) or root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid local model identifier or model root.")
    folder_name, filename = model_id.split("/")
    folder = root / folder_name
    model_path = folder / filename
    if (folder.is_symlink() or not folder.is_dir()
            or model_path.is_symlink() or not model_path.is_file()):
        raise ValueError("The model must exist as a regular file inside an approved folder.")
    registry = root / "annotations.json"
    if registry.is_symlink():
        raise ValueError("Registry symlinks are forbidden.")
    data = {key: value.model_dump(exclude_none=True) for key, value in read_annotations(root).items()}
    data[model_id] = annotation.model_dump(exclude_none=True)
    output = json.dumps({"schema_version": 1, "models": data}, ensure_ascii=False, indent=2)
    if len(output.encode("utf-8")) > MAX_ANNOTATIONS_BYTES:
        raise ValueError("Registry would exceed size limit.")
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root,
                                         prefix=".annotations-", suffix=".tmp", delete=False) as temp:
            path = Path(temp.name)
            temp.write(output)
            temp.flush()
            os.fsync(temp.fileno())
        path.replace(registry)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def infer_family(raw: str | None) -> ModelFamily | None:
    """Conservative hints from known SAI ModelSpec / trainer metadata labels."""
    if not raw:
        return None
    label = raw.strip().casefold()
    if (label.startswith("stable-diffusion-xl-v1")
            or label.startswith("stable-diffusion-xl-turbo")
            or label.startswith("sdxl_base") or label in ("sdxl", "sdxl_base_v1-0")):
        return "sdxl"
    if label.startswith("stable-diffusion-v1") or label.startswith("sd_v1"):
        return "sd15"
    if label.startswith("stable-diffusion-v2") or label.startswith("sd_v2"):
        return "sd2"
    if label.startswith("stable-diffusion-v3") or label.startswith("stable-diffusion-3"):
        return "sd3"
    if label.startswith("flux.1") or label.startswith("flux-1"):
        return "flux"
    return None
