"""Bounded, read-only inference dependency inventory; NEVER run a model or probe CUDA.

This is metadata inventory only, including when all packages are installed.
No imports of torch/diffusers/transformers and no access to CUDA, model weights,
network, pip, environment secrets or local filesystem paths.
"""
from __future__ import annotations

from importlib import metadata
import re
from typing import Callable

# Fixed allow-list; never accept client-controlled package names or paths.
PACKAGES = ("torch", "diffusers", "transformers", "accelerate", "safetensors", "Pillow")
SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+!-]{0,63}\Z")


def dependency_inventory(
    read_version: Callable[[str], str] = metadata.version,
) -> dict:
    """Examine only installed-distribution metadata, not importable modules.

    Present package != compatible CUDA runtime or executable inference engine.
    Any unexpected metadata failure is explicitly unknown (never 'ready').
    """
    results: list[dict] = []
    for name in PACKAGES:
        version = None
        try:
            raw = read_version(name)
        except metadata.PackageNotFoundError:
            state = "missing"
        except Exception:
            state = "unknown"
        else:
            if isinstance(raw, str) and SAFE_VERSION.fullmatch(raw) is not None:
                state = "detected"
                version = raw
            else:
                state = "unknown"
        results.append({"package": name, "state": state, "version": version})

    return {
        "schema_version": 1,
        "method": "distribution_metadata_only",
        "readiness": "not_verified",
        "cuda_tested": False,
        "gpu_accessed": False,
        "models_opened": False,
        "downloads_performed": False,
        "packages": results,
    }
