"""M3-18: synthetic-only VRAM evidence tests, no CUDA or real GPU required."""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

import gpu_memory_observer as observer

GIB_MIB = 8192


def sample(used: int, gpu_index: int = 0, total: int = GIB_MIB):
    return observer.MemorySample(gpu_index, total, used, total - used)


def test_parses_strict_nvidia_smi_multi_gpu_sample_without_device_name():
    raw = "0, 8192, 2048, 6144\n1, 12288, 1024, 11264\n"
    assert observer.parse_gpu_memory_csv(raw, 0) == sample(2048)
    assert observer.parse_gpu_memory_csv(raw, 1) == observer.MemorySample(
        1, 12288, 1024, 11264
    )


@pytest.mark.parametrize("payload", [
    "0, 8192, N/A, N/A",
    "0, 8192, 2048",
    "0, 8192, 2048, 6144, extra",
    "0, 8192, -1, 8193",
    "0, 8192, 9000, 0",
    "0, 8192, 4096, 4099",
    "0, 0, 0, 0",
    "17, 8192, 2048, 6144",
    "0, 8192, 2048, 6144\n0, 8192, 3000, 5192",
    "0, 8192, 2048, 6144\nbad, 8192, 0, 8192",
    "0, 8192, 2048, 6144\nprivate/path",
])
def test_rejects_malformed_or_unavailable_gpu_memory(payload):
    with pytest.raises(ValueError):
        observer.parse_gpu_memory_csv(payload, 0)


def test_rejects_wrong_gpu_index_and_oversized_output():
    with pytest.raises(ValueError, match="gpu_index_missing"):
        observer.parse_gpu_memory_csv("0, 8192, 0, 8192", 1)
    with pytest.raises(ValueError):
        observer.parse_gpu_memory_csv("0, 8192, 0, 8192\n" + " " * 4200, 0)
    with pytest.raises(ValueError):
        observer.parse_gpu_memory_csv("0, 8192, 0, 8192", True)


def test_real_sampler_uses_fixed_readonly_nvidia_smi_command_and_no_shell(monkeypatch):
    seen = []
    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"0, 8192, 2048, 6144\n")
    monkeypatch.setattr(observer.subprocess, "run", fake_run)
    assert observer.read_gpu_memory(0).used_mib == 2048
    assert len(seen) == 1
    argv, flags = seen[0]
    assert argv == observer.GPU_QUERY
    assert flags["shell"] is False
    assert flags["stderr"] is subprocess.DEVNULL
    assert flags["stdin"] is subprocess.DEVNULL
    assert flags["timeout"] == observer.SAMPLE_TIMEOUT_SECONDS
    assert not any("prompt" in word for word in argv)


def test_unavailable_nvidia_smi_error_contains_no_system_paths(monkeypatch):
    def failed(*args, **kwargs):
        raise OSError(r"C:\Users\private\some_driver_secret")
    monkeypatch.setattr(observer.subprocess, "run", failed)
    with pytest.raises(ValueError) as error:
        observer.read_gpu_memory(0)
    assert str(error.value) == "nvidia_smi_unavailable"
    assert "private" not in str(error.value)


def test_gpu_sampling_reports_only_system_observations_not_verified_reclamation():
    values = iter([sample(1024), sample(4096), sample(2048), sample(1280)])
    sleeps = []
    report = observer.observe_gpu_memory(
        0, duration_seconds=10, interval_seconds=3,
        sampler=lambda _: next(values),
        sleeper=sleeps.append,
    )
    assert report["status"] == "system_memory_observed"
    assert report["sample_count"] == 4
    assert sleeps == [3, 3, 3]
    assert report["observed"] == {
        "total_mib_at_start": 8192,
        "used_mib_at_start": 1024,
        "used_mib_peak_sampled": 4096,
        "used_mib_at_end": 1280,
        "free_mib_at_end": 6912,
        "peak_minus_start_mib": 3072,
        "end_minus_start_mib": 256,
    }
    assert set(report["manual_checks"].values()) == {"not_tested"}
    assert report["evidence_scope"].endswith("_not_app_specific")
    assert "recovered" not in json.dumps(report)


def test_sampling_failure_preserves_partial_samples_without_claiming_success():
    iterator = iter([sample(1000), ValueError(r"C:\Users\private\hidden")])
    def next_sample(_):
        element = next(iterator)
        if isinstance(element, Exception):
            raise element
        return element
    report = observer.observe_gpu_memory(
        0, duration_seconds=10, interval_seconds=2, sampler=next_sample,
        sleeper=lambda _: None,
    )
    assert report["status"] == "sampling_interrupted"
    assert report["sample_count"] == 1
    assert report["error_category"] == "nvidia_smi_unavailable"
    assert report["observed"]["used_mib_at_start"] == 1000
    assert "private" not in json.dumps(report)


def test_changing_gpu_total_memory_causes_incomplete_report():
    series = iter([sample(1000), observer.MemorySample(0, 16384, 2000, 14384)])
    result = observer.observe_gpu_memory(
        0, 10, 2, sampler=lambda _: next(series),
        sleeper=lambda _: None,
    )
    assert result["status"] == "sampling_interrupted"
    assert result["error_category"] == "gpu_device_changed"


@pytest.mark.parametrize("duration, interval", [
    (0, 1), (901, 1), (10, 0), (10, 11), (True, 2),
])
def test_rejects_invalid_sampling_limits_without_query(duration, interval):
    def forbidden(*args):
        raise AssertionError("Invalid request must not invoke NVIDIA CLI")
    with pytest.raises(ValueError):
        observer.observe_gpu_memory(
            0, duration, interval, sampler=forbidden, sleeper=forbidden,
        )


def test_cli_requires_double_optin_and_rejects_excessive_duration(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No sampling without deliberate double opt-in")
    monkeypatch.setattr(observer, "observe_gpu_memory", forbidden)
    for args in (
        [],
        ["--observe"],
        ["--confirm-monitor"],
        ["--observe", "--confirm-monitor", "--duration-seconds", "1000"],
        ["--observe", "--confirm-monitor", "--interval-seconds", "0"],
    ):
        with pytest.raises(SystemExit) as failure:
            observer.main(args)
        assert failure.value.code == 2


def test_cli_emits_only_derived_json_from_mock_monitor(monkeypatch, capsys):
    def fake_observation(index, duration, interval):
        assert (index, duration, interval) == (0, 10, 2)
        return {"schema_version": 1, "status": "system_memory_observed",
                "observed": {"used_mib_peak_sampled": 4000}}
    monkeypatch.setattr(observer, "observe_gpu_memory", fake_observation)
    result = observer.main([
        "--observe", "--confirm-monitor",
        "--duration-seconds", "10", "--interval-seconds", "2",
    ])
    assert result == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["observed"]["used_mib_peak_sampled"] == 4000
