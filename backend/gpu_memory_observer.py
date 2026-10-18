"""M3-18: explicit, bounded owner-run NVIDIA GPU memory observation.

This is a read-only external-device observer, NOT a CUDA workload executor,
GPU reset utility, proof of full memory reclamation or automated benchmark.
No model/prompt/local path is accepted and no report is written to disk.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

SCHEMA_VERSION = 1
MIB = 1024 * 1024
MAX_GPU_MEMORY_MIB = 256 * 1024
MAX_OUTPUT_BYTES = 4096
SAMPLE_TIMEOUT_SECONDS = 4
MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 900
MIN_INTERVAL_SECONDS = 1
MAX_INTERVAL_SECONDS = 10
GPU_QUERY = (
    "nvidia-smi",
    "--query-gpu=index,memory.total,memory.used,memory.free",
    "--format=csv,noheader,nounits",
)


@dataclass(frozen=True)
class MemorySample:
    gpu_index: int
    total_mib: int
    used_mib: int
    free_mib: int


def parse_gpu_memory_csv(output: str, gpu_index: int) -> MemorySample:
    """Strict NVIDIA nvidia-smi CSV: MiB only, bounded and one selected GPU."""
    if type(gpu_index) is not int or not 0 <= gpu_index <= 16:
        raise ValueError("invalid_gpu_index")
    if type(output) is not str or len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("invalid_gpu_output")
    matched: MemorySample | None = None
    seen_indices: set[int] = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != 4 or any(not part.isascii() or not part.isdecimal() for part in fields):
            raise ValueError("invalid_gpu_output")
        index, total, used, free = map(int, fields)
        if index in seen_indices or not 0 <= index <= 16:
            raise ValueError("invalid_gpu_output")
        seen_indices.add(index)
        if not (0 < total <= MAX_GPU_MEMORY_MIB and 0 <= used <= total and 0 <= free <= total):
            raise ValueError("invalid_gpu_memory")
        # Reserved driver allocations may make (used + free) smaller than total.
        # Reject obviously inconsistent readings but not legitimate small gaps.
        if used + free > total + 2:
            raise ValueError("invalid_gpu_memory")
        if index == gpu_index:
            matched = MemorySample(index, total, used, free)
    if matched is None:
        raise ValueError("gpu_index_missing")
    return matched


def read_gpu_memory(gpu_index: int) -> MemorySample:
    """Use ONLY a fixed read-only NVIDIA CLI, never a shell or user command."""
    try:
        completed = subprocess.run(
            GPU_QUERY, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=SAMPLE_TIMEOUT_SECONDS,
            shell=False, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("nvidia_smi_unavailable") from None
    if completed.returncode != 0 or len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise ValueError("nvidia_smi_unavailable")
    try:
        stdout = completed.stdout.decode("ascii", errors="strict")
    except UnicodeError:
        raise ValueError("invalid_gpu_output") from None
    return parse_gpu_memory_csv(stdout, gpu_index)


def observe_gpu_memory(
    gpu_index: int, duration_seconds: int, interval_seconds: int,
    *, sampler: Callable[[int], MemorySample] = read_gpu_memory,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Sample system-level GPU memory only while the owner operates their UI.

    Returning close to baseline is an observation, NOT proof of job-specific
    CUDA reclamation; GPU usage from unrelated apps is not distinguished.
    """
    if type(duration_seconds) is not int or not MIN_DURATION_SECONDS <= duration_seconds <= MAX_DURATION_SECONDS:
        raise ValueError("invalid_duration")
    if type(interval_seconds) is not int or not MIN_INTERVAL_SECONDS <= interval_seconds <= MAX_INTERVAL_SECONDS:
        raise ValueError("invalid_interval")
    if type(gpu_index) is not int or not 0 <= gpu_index <= 16:
        raise ValueError("invalid_gpu_index")
    samples: list[MemorySample] = []
    requested_samples = duration_seconds // interval_seconds + 1
    error_category: str | None = None
    for i in range(requested_samples):
        try:
            sample = sampler(gpu_index)
            if not isinstance(sample, MemorySample) or sample.gpu_index != gpu_index:
                raise ValueError("invalid_gpu_output")
            if not (0 < sample.total_mib <= MAX_GPU_MEMORY_MIB
                    and 0 <= sample.used_mib <= sample.total_mib
                    and 0 <= sample.free_mib <= sample.total_mib
                    and sample.used_mib + sample.free_mib <= sample.total_mib + 2):
                raise ValueError("invalid_gpu_memory")
            if samples and sample.total_mib != samples[0].total_mib:
                raise ValueError("gpu_device_changed")
            samples.append(sample)
        except Exception as problem:
            allowed = {
                "invalid_gpu_index", "invalid_gpu_output", "invalid_gpu_memory",
                "gpu_index_missing", "gpu_device_changed", "nvidia_smi_unavailable",
            }
            category = str(problem)
            error_category = category if category in allowed else "nvidia_smi_unavailable"
            break
        if i < requested_samples - 1:
            sleeper(interval_seconds)

    result = {
        "schema_version": SCHEMA_VERSION,
        "milestone": "M3-18",
        "status": "sampling_interrupted" if error_category else "system_memory_observed",
        "gpu_index": gpu_index,
        "sample_count": len(samples),
        "requested_sample_count": requested_samples,
        "sample_interval_seconds": interval_seconds,
        "evidence_scope": "nvidia_smi_system_level_snapshot_series_not_app_specific",
        "manual_checks": {
            "visual_quality": "not_tested",
            "app_process_cleanup": "not_tested",
            "cuda_reclamation_causality": "not_tested",
            "offline_network_isolation": "not_tested",
        },
        "warnings": [
            "Windows WDDM/NVIDIA 드라이버에 따라 메모리 정보가 N/A일 수 있습니다.",
            "다른 프로그램의 GPU 메모리와 드라이버 예약도 포함될 수 있습니다.",
            "주기적 샘플은 순간 최대치나 앱 고유 CUDA 메모리 회수를 증명하지 않습니다.",
        ],
    }
    if error_category:
        result["error_category"] = error_category
    if samples:
        used = [s.used_mib for s in samples]
        result["observed"] = {
            "total_mib_at_start": samples[0].total_mib,
            "used_mib_at_start": used[0],
            "used_mib_peak_sampled": max(used),
            "used_mib_at_end": used[-1],
            "free_mib_at_end": samples[-1].free_mib,
            "peak_minus_start_mib": max(used) - used[0],
            "end_minus_start_mib": used[-1] - used[0],
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Owner-run read-only NVIDIA VRAM sample session. No model loading or GPU reset."
    )
    parser.add_argument("--observe", action="store_true",
                        help="Explicitly start system-level nvidia-smi sampling.")
    parser.add_argument("--confirm-monitor", action="store_true",
                        help="Confirm local monitoring; no uploads or model inference.")
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--duration-seconds", type=int, default=120)
    parser.add_argument("--interval-seconds", type=int, default=2)
    options = parser.parse_args(argv)
    if not (options.observe and options.confirm_monitor):
        parser.error("Monitoring requires BOTH --observe and --confirm-monitor.")
    if not 0 <= options.gpu_index <= 16:
        parser.error("--gpu-index must be in [0,16].")
    if not MIN_DURATION_SECONDS <= options.duration_seconds <= MAX_DURATION_SECONDS:
        parser.error("--duration-seconds must be 10..900.")
    if not MIN_INTERVAL_SECONDS <= options.interval_seconds <= MAX_INTERVAL_SECONDS:
        parser.error("--interval-seconds must be 1..10.")
    result = observe_gpu_memory(
        options.gpu_index, options.duration_seconds, options.interval_seconds
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "system_memory_observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
