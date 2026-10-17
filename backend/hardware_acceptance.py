"""M3-10: owner-operated, offline SDXL hardware acceptance evidence.

DEFAULT: metadata-only preflight, never imports Torch/Diffusers/CUDA.
Explicit --execute --confirm-gpu is required for real inference.
No model downloads, automatic uploads or detailed exception/path leakage.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from generate_sdxl import (
    GenerationSettings, MODEL_ROOT, OUTPUT_ROOT, MAX_PNG_BYTES,
    prepare_generation, run_generation, summarize_runtime_metrics,
)
from gpu_diagnostics import inspect_gpu

SCHEMA_VERSION = 1
SAFE_PNG_NAME = re.compile(r"aiimage-[0-9a-f]{32}\.png\Z")
MAX_SIDE = 1024

# Visual quality, actual total VRAM consumption and Windows process-tree
# cleanup cannot be established by an image-generation function's return.
MANUAL_CHECKS = {
    "visual_prompt_adherence": "not_tested",
    "total_gpu_vram_peak": "not_tested",
    "process_tree_cleanup": "not_tested",
    "network_offline_observation": "not_tested",
    "gui_interaction": "not_tested",
}


def _base_report() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "milestone": "M3-10",
        "status": "not_started",
        "offline_only": True,
        "gpu": {"status": "not_checked"},
        "model": {"sdxl_metadata": "not_checked", "config_found": False},
        "generation": {"status": "not_run"},
        "manual_checks": dict(MANUAL_CHECKS),
        "warnings": [
            "자동 검사는 이미지 품질, 전체 GPU VRAM 사용량 또는 프로세스 종료를 입증하지 않습니다."
        ],
    }


def _classify_failure(reason: Exception) -> str:
    """No raw exception text: exceptions may contain usernames/model paths."""
    msg = str(reason).lower()
    if "out of memory" in msg or "cuda oom" in msg:
        return "cuda_out_of_memory"
    if "cuda" in msg or "driver" in msg:
        return "cuda_runtime"
    if isinstance(reason, (ImportError, ModuleNotFoundError)):
        return "missing_dependency"
    if isinstance(reason, (OSError, PermissionError)):
        return "filesystem"
    return "inference_error"


def _gpu_summary(raw: dict[str, Any]) -> dict[str, Any]:
    status = raw.get("status", "cuda_probe_error")
    if status != "ready_for_trial":
        return {"status": str(status)[:40]}
    gpu = raw.get("gpu")
    if not isinstance(gpu, dict):
        return {"status": "cuda_probe_error"}
    return {
        "status": "ready_for_trial",
        "name": str(gpu.get("name", "unknown"))[:120],
        "compute_capability": str(gpu.get("compute_capability", "unknown"))[:12],
        "total_vram_bytes": int(gpu.get("total_vram_bytes", 0)),
        "free_vram_bytes_at_check": int(gpu.get("free_vram_bytes_at_check", 0)),
        "torch_version": str(raw.get("torch_version", "unknown"))[:96],
        "torch_cuda_build": str(raw.get("torch_cuda_build", "unknown"))[:64],
    }


def _verify_output(path: Path, root: Path, width: int, height: int) -> dict[str, Any]:
    """Pillow is optional in CI but REQUIRED when a real generation is run.

    Verify container, decoded pixels, fixed-root location, output dimensions
    and SHA-256. Do not report a successful artifact from a signature alone.
    """
    if root.is_symlink() or not root.is_dir() or path.is_symlink():
        raise ValueError("Unsafe output storage")
    root_real = root.resolve(strict=True)
    path_real = path.resolve(strict=True)
    if path_real.parent != root_real or not SAFE_PNG_NAME.fullmatch(path_real.name):
        raise ValueError("Unexpected output file path")
    size = path_real.stat().st_size
    if size < 45 or size > MAX_PNG_BYTES:
        raise ValueError("Output PNG size outside supported range")
    from PIL import Image  # Lazy; installed only with optional inference requirements.
    with Image.open(path_real) as img:
        if img.format != "PNG" or getattr(img, "n_frames", 1) != 1:
            raise ValueError("Output is not a static PNG")
        if img.size != (width, height) or not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
            raise ValueError("Unexpected output resolution")
        img.verify()
    with Image.open(path_real) as img:
        img.load()  # Actual pixel decompression, not just PNG header parsing.
        if img.size != (width, height):
            raise ValueError("Output dimensions changed during verification")
    digest = hashlib.sha256()
    with path_real.open("rb") as f:
        while chunk := f.read(64 * 1024):
            digest.update(chunk)
    return {
        "file_name": path_real.name,
        "width": width,
        "height": height,
        "size_bytes": size,
        "png_sha256": digest.hexdigest(),
        "validation": "pillow_decoded_and_sha256_checked",
    }


def run_acceptance(
    settings: GenerationSettings,
    *,
    model_root: Path = MODEL_ROOT,
    output_root: Path = OUTPUT_ROOT,
    execute: bool = False,
    confirmed: bool = False,
    inspect: bool = False,
    gpu_inspector: Callable[[], dict[str, Any]] | None = None,
    runner: Callable[..., Path] | None = None,
    verifier: Callable[[Path, Path, int, int], dict[str, Any]] | None = None,
    torch_loader: Callable[[str], Any] | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Produce sanitized JSON. Dependency injection keeps GitHub CI CPU-only."""
    report = _base_report()
    if execute and not confirmed:
        report["status"] = "confirmation_required"
        return report

    try:
        _, _, plan = prepare_generation(settings, model_root)
        report["model"]["sdxl_metadata"] = "hint_only"
        report["model"]["config_found"] = plan.config_found
        if not plan.config_found:
            report["status"] = "offline_config_missing"
            return report
    except (ValueError, OSError, RuntimeError):
        report["status"] = "model_preflight_failed"
        return report

    if not (inspect or execute):
        report["status"] = "preflight_ready_gpu_unchecked"
        return report

    try:
        raw = (gpu_inspector or inspect_gpu)()
        report["gpu"] = _gpu_summary(raw)
    except Exception:
        report["gpu"] = {"status": "cuda_probe_error"}
    if not execute:
        report["status"] = "gpu_probe_only"
        return report
    if report["gpu"]["status"] != "ready_for_trial":
        report["status"] = "gpu_not_ready"
        return report

    # No heavy inference dependencies are imported before explicit consent
    # AND a successful local model/config + CUDA preflight.
    try:
        torch = (torch_loader or importlib.import_module)("torch")
    except Exception:
        report["status"] = "missing_inference_dependency"
        return report

    cuda = getattr(torch, "cuda", None)
    if cuda is not None:
        try:
            if cuda.is_available():
                cuda.reset_peak_memory_stats()
        except Exception:
            cuda = None

    now = clock or time.perf_counter
    start = now()
    try:
        path = (runner or run_generation)(
            settings, model_root=model_root, output_root=output_root, torch_module=torch
        )
        elapsed = now() - start
        if not 0 <= elapsed <= 3600:
            raise ValueError("Invalid run duration")
        validated = (verifier or _verify_output)(path, output_root, settings.width, settings.height)
        metrics = summarize_runtime_metrics(path, elapsed, cuda)
        # Check integrity against the separately computed Python measurement.
        if metrics["output_png_sha256"] != validated["png_sha256"]:
            report["status"] = "image_validation_failed"
            return report
        report["generation"] = {
            "status": "saved_png_verified",
            **validated,
            "elapsed_seconds": metrics["elapsed_seconds"],
            "gpu_memory_measurement": metrics["gpu_memory_measurement"],
            "gpu_peak_allocated_bytes": metrics["gpu_peak_allocated_bytes"]
                if metrics["gpu_memory_measurement"] == "torch_cuda_allocator" else None,
            "gpu_peak_reserved_bytes": metrics["gpu_peak_reserved_bytes"]
                if metrics["gpu_memory_measurement"] == "torch_cuda_allocator" else None,
        }
        report["status"] = "generated_png_decoded"
    except Exception as error:
        report["status"] = "generation_failed"
        report["generation"] = {
            "status": "failed",
            "error_category": _classify_failure(error),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline SDXL QA report; dry preflight unless BOTH --execute and --confirm-gpu."
    )
    parser.add_argument("--checkpoint", required=True, help="Registered checkpoints/name.safetensors ID")
    parser.add_argument("--prompt", default="", help="Required for --execute; NEVER stored in QA JSON")
    parser.add_argument("--inspect-gpu", action="store_true", help="Inspect CUDA without loading a checkpoint")
    parser.add_argument("--execute", action="store_true", help="Explicit actual SDXL generation attempt")
    parser.add_argument("--confirm-gpu", action="store_true", help="Consent required with --execute")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--guidance", type=float, default=7.0)
    args = parser.parse_args(argv)
    if args.execute and not args.confirm_gpu:
        parser.error("--execute also requires --confirm-gpu")
    if args.execute and not args.prompt.strip():
        parser.error("--execute also requires --prompt")
    try:
        settings = GenerationSettings(
            checkpoint_id=args.checkpoint,
            prompt=args.prompt if args.execute else "Metadata preflight only",
            width=args.width, height=args.height, steps=args.steps,
            seed=args.seed, guidance_scale=args.guidance,
        )
    except ValueError:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "invalid_settings",
            "generation": {"status": "not_run"},
        }, ensure_ascii=False))
        return 2
    report = run_acceptance(
        settings, execute=args.execute, confirmed=args.confirm_gpu,
        inspect=args.inspect_gpu,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {
        "preflight_ready_gpu_unchecked", "gpu_probe_only", "generated_png_decoded"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
