"""M3-46: no-execution planning tests; never import CUDA/PyTorch or probe GPUs."""
import json

from runtime_plan import isolated_runtime_plan, torch_wheel_hint
from runtime_preflight import PACKAGES, dependency_inventory


def fake_inventory(torch_version):
    def version(name):
        if name == "torch":
            return torch_version
        return "0.38.2"
    return dependency_inventory(version)


def test_cuda_tag_is_only_package_metadata_not_device_compatibility():
    plan = fake_inventory("2.9.1+cu129")["setup_plan"]
    assert plan["torch_wheel_hint"] == {
        "kind": "cuda_wheel_metadata", "tag": "cu129",
        "hardware_compatibility_verified": False,
    }
    assert plan["inference_runtime_connection"] == "not_connected"
    assert plan["inspection_scope"] == "current_api_python_process_only"
    assert plan["gpu_probe_authorized"] is False
    assert plan["cuda_or_device_compatibility_verified"] is False
    assert plan["model_execution_verified"] is False
    assert plan["automated_package_installation"] is False
    assert plan["automatic_downloads_enabled"] is False
    assert plan["installation_mode"] == "manual_only"
    assert len(plan["setup_steps"]) == 4
    json.dumps(plan)


def test_cpu_tag_and_version_without_build_tag_stay_nonready():
    cpu = fake_inventory("2.9.1+cpu")["setup_plan"]
    assert cpu["torch_wheel_hint"]["kind"] == "cpu_wheel_metadata"
    assert cpu["torch_wheel_hint"]["tag"] == "cpu"
    plain = fake_inventory("2.9.1")["setup_plan"]
    assert plain["torch_wheel_hint"]["kind"] == "unknown"
    assert plain["torch_wheel_hint"]["tag"] is None
    assert cpu["inference_runtime_connection"] == plain["inference_runtime_connection"] == "not_connected"


def test_invalid_or_malicious_wheel_tags_never_become_commands_or_urls():
    for version in ["3.0+cu129&&whoami", "3.0+cuda129", "3.0+cu129\nsecret", "3.0+cu129/relative", "3.0+cu", "../private/keys", "3.0+rocm", ""]:
        plan = fake_inventory(version)["setup_plan"]
        assert plan["torch_wheel_hint"]["kind"] == "unknown"
        assert plan["torch_wheel_hint"]["tag"] is None
        assert "whoami" not in json.dumps(plan)
        assert "private/keys" not in json.dumps(plan)


def test_all_detected_still_does_not_prove_separate_environment_exists():
    versions = {name: "2.9.1+cu129" if name == "torch" else "0.40.0" for name in PACKAGES}
    data = dependency_inventory(lambda name: versions[name])
    assert all(p["state"] == "detected" for p in data["packages"])
    assert data["readiness"] == "not_verified"
    assert data["setup_plan"]["inference_runtime_connection"] == "not_connected"
    assert data["setup_plan"]["preferred_python_version"] == "3.12"
    assert list(data["setup_plan"]["documentation"]) == ["python_venv", "pytorch_windows"]


def test_plan_accepts_missing_torch_metadata_but_never_runs_it():
    plan = isolated_runtime_plan({"packages": [{"package": "torch", "state": "missing", "version": None}]})
    assert plan["torch_wheel_hint"]["tag"] is None
    assert plan["gpu_probe_authorized"] is False
    assert plan["recommended_isolation"] == "separate_python_virtual_environment"
