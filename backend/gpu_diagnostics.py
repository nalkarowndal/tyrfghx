"""M3-6 local GPU readiness inspection. No network, downloads or model inference.

This script can initialize a CUDA driver context to collect device details,
but does not load checkpoint weights or allocate inference tensors.
"""
from __future__ import annotations

import argparse
import importlib
import json
import platform
from typing import Any

SCHEMA_VERSION = 1
MIB = 1024 * 1024
GIB = 1024 * MIB


def _empty_report() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "os": platform.system(),
        "torch_version": None,
        "torch_cuda_build": None,
        "gpu": None,
        "warnings": [
            "이 검사는 이미지 생성, VRAM 최대 사용량, 모델 호환성을 검증하지 않습니다."
        ],
        "trial_settings": {
            "width": 512,
            "height": 512,
            "steps": 15,
            "images": 1,
            "cpu_offload": True,
        },
    }


def inspect_gpu(torch_module=None) -> dict[str, Any]:
    """Return a bounded, versioned JSON-compatible report without reading user data.

    A torch_module parameter makes this testable without PyTorch/CUDA in CI.
    Import/driver exceptions are intentionally not echoed with local paths.
    """
    report = _empty_report()
    if torch_module is None:
        try:
            torch_module = importlib.import_module("torch")
        except ImportError:
            report["status"] = "torch_missing"
            report["warnings"].append("PyTorch 미설치: 별도 CUDA 지원 빌드가 필요합니다.")
            return report
        except Exception:
            report["status"] = "torch_import_error"
            report["warnings"].append("PyTorch 초기화 실패: Python 환경을 확인하세요.")
            return report

    report["torch_version"] = str(getattr(torch_module, "__version__", "unknown"))[:96]
    version = getattr(torch_module, "version", None)
    cuda_build = getattr(version, "cuda", None)
    hip_build = getattr(version, "hip", None)
    report["torch_cuda_build"] = str(cuda_build)[:64] if cuda_build else None
    if hip_build:
        report["status"] = "unsupported_backend"
        report["warnings"].append("ROCm/HIP 백엔드는 현재 Windows CUDA 실행기의 검증 대상이 아닙니다.")
        return report
    if not cuda_build:
        report["status"] = "cpu_only_torch"
        report["warnings"].append("현재 PyTorch 빌드에 CUDA 지원이 없습니다.")
        return report
    try:
        if not torch_module.cuda.is_available():
            report["status"] = "cuda_unavailable"
            report["warnings"].append("CUDA 장치를 사용할 수 없습니다. 드라이버와 PyTorch 설치를 확인하세요.")
            return report
        count = int(torch_module.cuda.device_count())
        if count <= 0:
            report["status"] = "cuda_unavailable"
            report["warnings"].append("PyTorch가 사용할 GPU를 찾지 못했습니다.")
            return report
        index = int(torch_module.cuda.current_device())
        properties = torch_module.cuda.get_device_properties(index)
        free, total = torch_module.cuda.mem_get_info(index)
        total = int(total)
        free = int(free)
        if not 0 <= free <= total or total <= 0:
            raise ValueError("Invalid GPU memory measurement")
        name = str(getattr(properties, "name", "Unknown GPU"))[:120]
        major = int(getattr(properties, "major", 0))
        minor = int(getattr(properties, "minor", 0))
        report["gpu"] = {
            "index": index,
            "name": name,
            "compute_capability": f"{major}.{minor}",
            "total_vram_bytes": total,
            "free_vram_bytes_at_check": free,
        }
        report["status"] = "ready_for_trial"
        if free < 5 * GIB:
            report["warnings"].append("사용 가능한 VRAM이 5GiB 미만입니다. 다른 GPU 프로그램을 종료한 뒤 테스트하세요.")
        if total <= 8 * GIB:
            report["warnings"].append("8GiB급 GPU에서 SDXL 생성은 메모리 부족이나 느린 처리 속도가 발생할 수 있습니다.")
    except Exception:
        report["status"] = "cuda_probe_error"
        report["gpu"] = None
        report["warnings"].append("CUDA 정보 수집에 실패했습니다. 드라이버와 Python 환경을 확인하세요.")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect local CUDA environment; no model inference.")
    parser.add_argument("--strict", action="store_true",
                        help="Exit nonzero unless CUDA is detected. Detection does not guarantee inference.")
    options = parser.parse_args(argv)
    report = inspect_gpu()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if options.strict and report["status"] != "ready_for_trial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
