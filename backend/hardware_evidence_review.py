"""M3-19: owner-only offline cross-check of local SDXL and GPU reports.

Does not run models, invoke NVIDIA CLI, inspect images, or certify a GPU.
Inputs are user-selected local JSON evidence; summaries are self-reported,
unverified metadata until the operator independently examines the device.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 64 * 1024
MAX_MIB = 256 * 1024
ACCEPTANCE_STATUSES = frozenset({
    "generated_png_decoded", "preflight_ready_gpu_unchecked",
    "gpu_probe_only", "vram_safety_blocked", "generation_failed",
    "gpu_not_ready", "model_preflight_failed", "offline_config_missing",
    "image_validation_failed", "missing_inference_dependency",
    "confirmation_required", "invalid_settings",
})
VRAM_STATUSES = frozenset({"system_memory_observed", "sampling_interrupted"})
MANUAL_CHECKS = (
    "visual_prompt_adherence", "windows_process_tree_cleanup",
    "app_specific_cuda_vram_reclamation", "gui_interaction",
    "offline_network_isolation", "evidence_matches_same_session",
)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate_json_field")
        output[key] = value
    return output


def _invalid_number(_: str) -> None:
    raise ValueError("non_standard_json_number")


def load_local_evidence(path: Path) -> tuple[dict[str, Any], str]:
    """Read at most 64KiB; never print the input path or raw payload."""
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe_evidence_file")
        with path.open("rb") as stream:
            payload = stream.read(MAX_INPUT_BYTES + 1)
    except (OSError, RuntimeError):
        raise ValueError("cannot_read_evidence") from None
    if not payload or len(payload) > MAX_INPUT_BYTES:
        raise ValueError("evidence_size_invalid")
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_invalid_number,
        )
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("evidence_json_invalid") from None
    if type(decoded) is not dict:
        raise ValueError("evidence_schema_invalid")
    return decoded, hashlib.sha256(payload).hexdigest()


def _strict_int(value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("evidence_measurement_invalid")
    return value


def _read_acceptance(source: dict[str, Any]) -> dict[str, Any]:
    if type(source.get("schema_version")) is not int or source["schema_version"] != 1:
        raise ValueError("acceptance_version_unsupported")
    if source.get("milestone") != "M3-10" or source.get("status") not in ACCEPTANCE_STATUSES:
        raise ValueError("acceptance_schema_invalid")
    generation = source.get("generation")
    if type(generation) is not dict:
        raise ValueError("acceptance_schema_invalid")
    result = {
        "source_status": source["status"],
        "source_generation_status": "not_verified",
        "png_claimed_by_source": False,
    }
    if source["status"] == "generated_png_decoded":
        if generation.get("status") != "saved_png_verified":
            raise ValueError("acceptance_status_inconsistent")
        digest = generation.get("png_sha256")
        file_name = generation.get("file_name")
        if (type(digest) is not str or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
                or type(file_name) is not str
                or not file_name.startswith("aiimage-")
                or not file_name.endswith(".png")
                or len(file_name) != len("aiimage-") + 32 + 4
                or any(ch not in "0123456789abcdef" for ch in file_name[8:-4])):
            raise ValueError("acceptance_png_claim_invalid")
        _strict_int(generation.get("width"), 1, 1024)
        _strict_int(generation.get("height"), 1, 1024)
        _strict_int(generation.get("size_bytes"), 45, 8 * 1024 * 1024)
        result["source_generation_status"] = "source_claims_decoded_png_sha256"
        result["png_claimed_by_source"] = True
        result["png_sha256_reported"] = digest
        result["reported_width"] = generation["width"]
        result["reported_height"] = generation["height"]
    else:
        if generation.get("status") == "saved_png_verified":
            raise ValueError("acceptance_status_inconsistent")
        result["source_generation_status"] = "not_successfully_verified_by_source"
    return result


def _read_observer(source: dict[str, Any]) -> dict[str, Any]:
    if (type(source.get("schema_version")) is not int
            or source["schema_version"] != 1
            or source.get("milestone") != "M3-18"
            or source.get("status") not in VRAM_STATUSES
            or source.get("evidence_scope")
            != "nvidia_smi_system_level_snapshot_series_not_app_specific"):
        raise ValueError("vram_schema_invalid")
    gpu_index = _strict_int(source.get("gpu_index"), 0, 16)
    samples = _strict_int(source.get("sample_count"), 0, 901)
    requested = _strict_int(source.get("requested_sample_count"), 1, 901)
    interval = _strict_int(source.get("sample_interval_seconds"), 1, 10)
    if samples > requested or (source["status"] == "system_memory_observed" and samples != requested):
        raise ValueError("vram_samples_inconsistent")
    result = {
        "source_status": source["status"],
        "gpu_index_reported": gpu_index,
        "sample_count_reported": samples,
        "requested_sample_count_reported": requested,
        "sample_interval_seconds_reported": interval,
    }
    observed = source.get("observed")
    if samples:
        if type(observed) is not dict:
            raise ValueError("vram_measurement_missing")
        total = _strict_int(observed.get("total_mib_at_start"), 1, MAX_MIB)
        start = _strict_int(observed.get("used_mib_at_start"), 0, total)
        end = _strict_int(observed.get("used_mib_at_end"), 0, total)
        peak = _strict_int(observed.get("used_mib_peak_sampled"), 0, total)
        free = _strict_int(observed.get("free_mib_at_end"), 0, total)
        if (peak < start or peak < end or
                end + free > total + 2 or
                observed.get("peak_minus_start_mib") != peak - start or
                observed.get("end_minus_start_mib") != end - start):
            raise ValueError("vram_measurement_inconsistent")
        result["observed_system_mib"] = {
            "total_at_start": total,
            "used_at_start": start,
            "used_peak_sampled": peak,
            "used_at_end": end,
            "free_at_end": free,
            "end_minus_start": end - start,
        }
    elif observed is not None:
        raise ValueError("vram_measurement_inconsistent")
    return result


def summarize_hardware_evidence(
    acceptance: dict[str, Any], observer: dict[str, Any],
    acceptance_sha256: str, observer_sha256: str,
) -> dict[str, Any]:
    """Not a hardware qualification: evidence still needs independent review."""
    a = _read_acceptance(acceptance)
    v = _read_observer(observer)
    both_complete = (a["png_claimed_by_source"] and
                     v["source_status"] == "system_memory_observed")
    return {
        "schema_version": 1,
        "milestone": "M3-19",
        "status": "evidence_available_for_manual_review" if both_complete else
                  "incomplete_evidence",
        "automatic_hardware_acceptance": "not_performed",
        "sources": {
            "generation": {"sha256_of_input_json": acceptance_sha256, **a},
            "system_gpu_memory": {"sha256_of_input_json": observer_sha256, **v},
        },
        "manual_checks": {key: "not_tested" for key in MANUAL_CHECKS},
        "limitations": [
            "입력 JSON은 사용자가 제공한 보고서이며 이 도구가 실제 GPU 실행 여부를 독립적으로 검증하지 않았습니다.",
            "PNG의 실제 픽셀과 해시를 다시 읽지 않았습니다. 원본 파일을 별도로 확인해야 합니다.",
            "두 보고서가 동일 GPU 또는 동일 생성 세션에서 수집됐다는 증거가 없습니다.",
            "nvidia-smi 메모리는 시스템 전체의 간헐적 샘플이며 앱 고유 VRAM 회수 증거가 아닙니다.",
            "시각적 품질, Windows 자식 프로세스 정리, 네트워크 격리, 앱 조작은 사람이 검수해야 합니다.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Owner-only offline report review. Does NOT execute CUDA or certify hardware."
    )
    parser.add_argument("--generation-json", type=Path, required=True)
    parser.add_argument("--gpu-memory-json", type=Path, required=True)
    parser.add_argument("--confirm-review", action="store_true",
                        help="Deliberately read these two local evidence files.")
    args = parser.parse_args(argv)
    if not args.confirm_review:
        parser.error("Explicit --confirm-review is required to read local files.")
    try:
        a, a_hash = load_local_evidence(args.generation_json)
        v, v_hash = load_local_evidence(args.gpu_memory_json)
        report = summarize_hardware_evidence(a, v, a_hash, v_hash)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["status"] == "evidence_available_for_manual_review" else 2
    except (ValueError, TypeError, OverflowError) as error:
        # Only our static fault codes are allowed; never print input paths.
        allowed = {
            "unsafe_evidence_file", "cannot_read_evidence", "evidence_size_invalid",
            "evidence_json_invalid", "evidence_schema_invalid", "duplicate_json_field",
            "non_standard_json_number", "evidence_measurement_invalid",
            "acceptance_version_unsupported", "acceptance_schema_invalid",
            "acceptance_status_inconsistent", "acceptance_png_claim_invalid",
            "vram_schema_invalid", "vram_samples_inconsistent",
            "vram_measurement_missing", "vram_measurement_inconsistent",
        }
        code = str(error)
        print(json.dumps({
            "schema_version": 1, "milestone": "M3-19",
            "status": "invalid_evidence",
            "error_code": code if code in allowed else "evidence_schema_invalid",
            "automatic_hardware_acceptance": "not_performed",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
