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
GIB = 1024 ** 3
MIN_FREE_VRAM_BYTES = 4 * GIB
MIN_TOTAL_VRAM_BYTES = 6 * GIB
LOW_VRAM_MAX_PIXELS = 768 * 768
MAX_VRAM_BYTES = 256 * GIB

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
        "memory_policy": {"status": "not_checked", "acknowledged": False},
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
    """Bound device values before displaying them or making a safety decision."""
    if not isinstance(raw, dict):
        return {"status": "cuda_probe_error"}
    status = raw.get("status", "cuda_probe_error")
    if status != "ready_for_trial":
        allowed = {
            "torch_missing", "torch_import_error", "cpu_only_torch",
            "unsupported_backend", "cuda_unavailable", "cuda_probe_error",
            "unavailable",
        }
        return {"status": status if status in allowed else "cuda_probe_error"}
    gpu = raw.get("gpu")
    if not isinstance(gpu, dict):
        return {"status": "cuda_probe_error"}
    try:
        total = gpu["total_vram_bytes"]
        free = gpu["free_vram_bytes_at_check"]
        if type(total) is not int or type(free) is not int:
            return {"status": "cuda_probe_error"}
        if not 0 <= free <= total <= MAX_VRAM_BYTES or total == 0:
            return {"status": "cuda_probe_error"}
        index = gpu.get("index", 0)
        if type(index) is not int or not 0 <= index <= 16:
            return {"status": "cuda_probe_error"}
    except (KeyError, TypeError, ValueError):
        return {"status": "cuda_probe_error"}
    # Do not repeat arbitrary diagnostic metadata, local filesystem paths or
    # device-defined multiline text in the sanitized acceptance report.
    def safe_label(text: Any, limit: int) -> str:
        value = str(text)
        return "".join(c for c in value if c.isprintable() and c not in "\\/:").strip()[:limit]
    return {
        "status": "ready_for_trial",
        "name": safe_label(gpu.get("name", "unknown"), 120),
        "compute_capability": safe_label(gpu.get("compute_capability", "unknown"), 12),
        "total_vram_bytes": total,
        "free_vram_bytes_at_check": free,
        "torch_version": safe_label(raw.get("torch_version") or "unknown", 96),
        "torch_cuda_build": safe_label(raw.get("torch_cuda_build") or "unknown", 64),
    }


def evaluate_memory_policy(
    settings: GenerationSettings, gpu: dict[str, Any],
    *, acknowledge_vram_risk: bool = False,
) -> dict[str, Any]:
    """Conservative trial heuristics, NOT an SDXL compatibility guarantee.

    Acknowledgement never bypasses missing CUDA or a nonsensical device
    report. Thresholds are deliberately geared to an 8GiB Windows card.
    """
    if gpu.get("status") != "ready_for_trial":
        return {"status": "gpu_not_ready", "acknowledged": False}
    total = gpu["total_vram_bytes"]
    free = gpu["free_vram_bytes_at_check"]
    low_total = total < MIN_TOTAL_VRAM_BYTES
    low_free = free < MIN_FREE_VRAM_BYTES
    high_resolution = total <= 8 * GIB and settings.width * settings.height > LOW_VRAM_MAX_PIXELS
    reasons = [
        name for name, active in (
            ("total_vram_under_6gib", low_total),
            ("free_vram_under_4gib", low_free),
            ("high_resolution_on_8gib", high_resolution),
        ) if active
    ]
    return {
        "status": "allowed_with_acknowledged_risk" if reasons and acknowledge_vram_risk else
                  "blocked" if reasons else "conservative_trial_allowed",
        "acknowledged": bool(reasons and acknowledge_vram_risk),
        "reasons": reasons,
        "suggested_width": 512,
        "suggested_height": 512,
        "suggested_steps": 15,
        "safety_note": "These checks are heuristics, not proof that inference will fit VRAM.",
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
    acknowledge_vram_risk: bool = False,
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
    policy = evaluate_memory_policy(
        settings, report["gpu"], acknowledge_vram_risk=acknowledge_vram_risk and confirmed and execute,
    )
    report["memory_policy"] = policy
    if not execute:
        report["status"] = "gpu_probe_only"
        return report
    if report["gpu"]["status"] != "ready_for_trial":
        report["status"] = "gpu_not_ready"
        return report
    if policy["status"] == "blocked":
        report["status"] = "vram_safety_blocked"
        return report
    if policy["status"] == "allowed_with_acknowledged_risk":
        report["warnings"].append(
            "VRAM 부족 또는 고해상도 위험을 사용자가 명시적으로 수락했습니다. 생성 성공은 보장되지 않습니다."
        )

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
    parser.add_argument("--acknowledge-vram-risk", action="store_true",
                        help="Extra acknowledgement to attempt inference with low GPU memory or high 8GiB-card resolution.")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--guidance", type=float, default=7.0)
    args = parser.parse_args(argv)
    if args.execute and not args.confirm_gpu:
        parser.error("--execute also requires --confirm-gpu")
    if args.acknowledge_vram_risk and not (args.execute and args.confirm_gpu):
        parser.error("--acknowledge-vram-risk requires --execute --confirm-gpu")
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
        acknowledge_vram_risk=args.acknowledge_vram_risk,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {
        "preflight_ready_gpu_unchecked", "gpu_probe_only", "generated_png_decoded"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
