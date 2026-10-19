"""M3-46: pure, non-executable compatibility guidance for isolated AI runtimes.

Only interpret already-sanitized *current API process* distribution metadata.
No Python environment discovery, GPU probing, subprocess, installs or file IO.
"""
from __future__ import annotations

import re

# Interpret metadata only. A CUDA suffix is NOT proof of the device, driver,
# kernel support, or that this is the environment used for AI generation.
_CUDA_SUFFIX = re.compile(r"cu[0-9]{3,4}\Z")


def torch_wheel_hint(inventory: dict) -> dict:
    """Parse a fixed PyTorch distribution tag without importing torch."""
    version = None
    for entry in inventory.get("packages", []):
        if entry.get("package") == "torch" and entry.get("state") == "detected":
            version = entry.get("version")
            break
    kind, tag = "unknown", None
    if isinstance(version, str) and len(version) <= 64:
        _, plus, suffix = version.partition("+")
        if plus and _CUDA_SUFFIX.fullmatch(suffix):
            kind, tag = "cuda_wheel_metadata", suffix
        elif plus and suffix == "cpu":
            kind, tag = "cpu_wheel_metadata", suffix
    return {
        "kind": kind,
        "tag": tag,
        "hardware_compatibility_verified": False,
    }


def isolated_runtime_plan(inventory: dict) -> dict:
    """Static advice: never derive executable commands from detected versions."""
    return {
        "schema_version": 1,
        "inspection_scope": "current_api_python_process_only",
        "inference_runtime_connection": "not_connected",
        "recommended_isolation": "separate_python_virtual_environment",
        "preferred_python_version": "3.12",
        "installation_mode": "manual_only",
        "automatic_downloads_enabled": False,
        "automated_package_installation": False,
        "gpu_probe_authorized": False,
        "cuda_or_device_compatibility_verified": False,
        "model_execution_verified": False,
        "torch_wheel_hint": torch_wheel_hint(inventory),
        "setup_steps": [
            "choose_isolated_python_runtime",
            "review_official_pytorch_windows_cuda_selector",
            "review_dependency_compatibility_and_disk_budget",
            "request_explicit_consent_before_gpu_diagnostics",
        ],
        "documentation": {
            "python_venv": "https://docs.python.org/3/library/venv.html",
            "pytorch_windows": "https://pytorch.org/get-started/locally/",
        },
    }
