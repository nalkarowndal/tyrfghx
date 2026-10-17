"""Mock-only GPU diagnostics contract checks; never initializes real CUDA in CI."""
from __future__ import annotations

from types import SimpleNamespace

from gpu_diagnostics import GIB, inspect_gpu


class FakeCuda:
    def __init__(self, available=True, free=6 * GIB, total=8 * GIB):
        self.available = available
        self.free = free
        self.total = total

    def is_available(self):
        return self.available

    def device_count(self):
        return 1

    def current_device(self):
        return 0

    def get_device_properties(self, index):
        assert index == 0
        return SimpleNamespace(name="Mock RTX 2060 SUPER", major=7, minor=5)

    def mem_get_info(self, index):
        assert index == 0
        return self.free, self.total


def mock_torch(cuda_build="12.8", hip_build=None, cuda=None):
    return SimpleNamespace(
        __version__="2.9.0+cu128",
        version=SimpleNamespace(cuda=cuda_build, hip=hip_build),
        cuda=FakeCuda() if cuda is None else cuda,
    )


def test_supported_cuda_report_includes_counts_and_no_model_paths():
    report = inspect_gpu(mock_torch())
    assert report["schema_version"] == 1
    assert report["status"] == "ready_for_trial"
    assert report["gpu"]["compute_capability"] == "7.5"
    assert report["gpu"]["total_vram_bytes"] == 8 * GIB
    assert report["gpu"]["free_vram_bytes_at_check"] == 6 * GIB
    assert report["trial_settings"]["width"] == 512
    assert "model_path" not in str(report)
    assert "검증하지" in report["warnings"][0]


def test_cpu_only_build():
    report = inspect_gpu(mock_torch(cuda_build=None))
    assert report["status"] == "cpu_only_torch"
    assert report["gpu"] is None


def test_rocm_build_is_not_misidentified_as_cuda():
    report = inspect_gpu(mock_torch(cuda_build=None, hip_build="6.2"))
    assert report["status"] == "unsupported_backend"


def test_missing_cuda_device():
    report = inspect_gpu(mock_torch(cuda=FakeCuda(available=False)))
    assert report["status"] == "cuda_unavailable"
    assert report["gpu"] is None


def test_insufficient_free_vram_warning():
    report = inspect_gpu(mock_torch(cuda=FakeCuda(free=2 * GIB)))
    assert any("5GiB" in line for line in report["warnings"])


def test_bad_cuda_probe_never_leaks_traceback():
    class BrokenCuda(FakeCuda):
        def mem_get_info(self, index):
            raise RuntimeError(r"C:\Users\secret\private.ckpt")
    report = inspect_gpu(mock_torch(cuda=BrokenCuda()))
    assert report["status"] == "cuda_probe_error"
    assert "private.ckpt" not in str(report)


def test_impossible_memory_report_is_rejected():
    report = inspect_gpu(mock_torch(cuda=FakeCuda(free=9 * GIB, total=8 * GIB)))
    assert report["status"] == "cuda_probe_error"


def test_missing_torch_import(monkeypatch):
    import gpu_diagnostics
    def absent(name):
        raise ImportError("torch")
    monkeypatch.setattr(gpu_diagnostics.importlib, "import_module", absent)
    report = inspect_gpu()
    assert report["status"] == "torch_missing"
