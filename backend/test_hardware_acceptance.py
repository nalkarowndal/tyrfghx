"""M3-10 offline QA: synthetic fixtures only; zero CUDA/model inference in CI."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from generate_sdxl import GenerationSettings
from hardware_acceptance import _verify_output, main, run_acceptance


def fixture_model(root: Path, *, config: bool = True) -> None:
    folder = root / "checkpoints"
    folder.mkdir()
    payload = json.dumps({
        "__metadata__": {"modelspec.architecture": "stable-diffusion-xl-v1-base"}
    }).encode()
    (folder / "mock.safetensors").write_bytes(
        struct.pack("<Q", len(payload)) + payload + b"\0" * 16
    )
    if config:
        path = root / "configs" / "sdxl-base-1.0"
        path.mkdir(parents=True)
        (path / "model_index.json").write_text(
            '{"_class_name":"StableDiffusionXLPipeline"}'
        )


def settings(prompt: str = "Private sample prompt") -> GenerationSettings:
    return GenerationSettings(
        checkpoint_id="checkpoints/mock.safetensors", prompt=prompt,
        width=512, height=512, steps=15, seed=42
    )


def gpu_report():
    return {
        "status": "ready_for_trial",
        "torch_version": "test-torch",
        "torch_cuda_build": "test-cuda",
        "gpu": {
            "index": 0, "name": "Synthetic RTX 2060 SUPER",
            "compute_capability": "7.5", "total_vram_bytes": 8 * 1024**3,
            "free_vram_bytes_at_check": 6 * 1024**3,
        },
    }


def test_default_preflight_never_imports_torch_or_runs_inference(tmp_path):
    fixture_model(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("No heavy module or model is allowed in default mode")
    report = run_acceptance(
        settings(), model_root=tmp_path, output_root=tmp_path / "outputs",
        torch_loader=forbidden, gpu_inspector=forbidden, runner=forbidden,
    )
    assert report["status"] == "preflight_ready_gpu_unchecked"
    assert report["gpu"]["status"] == "not_checked"
    assert report["generation"]["status"] == "not_run"
    assert report["model"]["sdxl_metadata"] == "hint_only"
    assert not (tmp_path / "outputs").exists()
    assert "Private sample prompt" not in json.dumps(report)


def test_missing_offline_config_stops_before_gpu_inspection(tmp_path):
    fixture_model(tmp_path, config=False)
    def forbidden():
        raise AssertionError("GPU must not be inspected when offline config is missing")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        gpu_inspector=forbidden,
    )
    assert report["status"] == "offline_config_missing"


def test_execution_requires_explicit_confirmation_even_in_python_api(tmp_path):
    def forbidden():
        raise AssertionError("GPU must not be accessed without consent")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=False,
        gpu_inspector=forbidden,
    )
    assert report["status"] == "confirmation_required"


def test_gpu_probe_only_does_not_invoke_runner(tmp_path):
    fixture_model(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected inference in hardware probe mode")
    report = run_acceptance(
        settings(), model_root=tmp_path, inspect=True,
        gpu_inspector=gpu_report, runner=forbidden, torch_loader=forbidden,
    )
    assert report["status"] == "gpu_probe_only"
    assert report["gpu"]["compute_capability"] == "7.5"
    assert report["manual_checks"]["visual_prompt_adherence"] == "not_tested"


def test_cuda_unavailable_refuses_inference(tmp_path):
    fixture_model(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Model should never load")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        gpu_inspector=lambda: {"status": "cuda_unavailable"},
        runner=forbidden, torch_loader=forbidden,
    )
    assert report["status"] == "gpu_not_ready"


class MockCuda:
    def __init__(self):
        self.reset = False

    def is_available(self):
        return True

    def reset_peak_memory_stats(self):
        self.reset = True

    def synchronize(self):
        pass

    def max_memory_allocated(self):
        return 2_000_000_000

    def max_memory_reserved(self):
        return 3_000_000_000


def test_explicit_mock_inference_produces_sanitized_bounded_evidence(tmp_path):
    fixture_model(tmp_path)
    cuda = MockCuda()
    def fake_runner(request, *, model_root, output_root, torch_module):
        assert cuda.reset
        assert torch_module.cuda is cuda
        output_root.mkdir()
        name = "aiimage-" + "a" * 32 + ".png"
        result = output_root / name
        result.write_bytes(b"synthetic PNG result; NO actual image or CUDA")
        return result

    def fake_verifier(image_path, root, width, height):
        assert (width, height) == (512, 512)
        return {
            "file_name": image_path.name, "width": width, "height": height,
            "size_bytes": image_path.stat().st_size,
            "png_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "validation": "mock_validator_not_actual_PNG",
        }

    report = run_acceptance(
        settings(), model_root=tmp_path, output_root=tmp_path / "outputs",
        execute=True, confirmed=True, gpu_inspector=gpu_report,
        torch_loader=lambda name: SimpleNamespace(cuda=cuda),
        runner=fake_runner, verifier=fake_verifier,
        clock=iter([1.0, 2.5]).__next__,
    )
    assert report["status"] == "generated_png_decoded"
    assert report["generation"]["elapsed_seconds"] == 1.5
    assert report["generation"]["gpu_peak_reserved_bytes"] == 3_000_000_000
    assert report["generation"]["file_name"].endswith(".png")
    assert report["manual_checks"]["total_gpu_vram_peak"] == "not_tested"
    output = json.dumps(report)
    assert "Private sample prompt" not in output
    assert str(tmp_path) not in output
    assert "synthetic PNG result" not in output


def test_missing_torch_or_sensitive_exception_never_leaks_details(tmp_path):
    fixture_model(tmp_path)
    secret = r"C:\Users\private\my_image.safetensors"
    def unavailable(_):
        raise OSError(secret)
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        gpu_inspector=gpu_report, torch_loader=unavailable,
    )
    assert report["status"] == "missing_inference_dependency"
    assert secret not in json.dumps(report)


def test_mock_runner_out_of_memory_is_classified_without_traceback(tmp_path):
    fixture_model(tmp_path)
    def oom(*args, **kwargs):
        raise RuntimeError("CUDA out of memory in " + r"C:\private\secret.ckpt")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        gpu_inspector=gpu_report,
        torch_loader=lambda _: SimpleNamespace(cuda=MockCuda()),
        runner=oom,
    )
    assert report["status"] == "generation_failed"
    assert report["generation"]["error_category"] == "cuda_out_of_memory"
    assert "secret.ckpt" not in json.dumps(report)


def test_verifier_rejects_external_and_symlink_paths_before_loading_pillow(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir()
    outside = tmp_path / ("aiimage-" + "b" * 32 + ".png")
    outside.write_bytes(b"not a PNG" * 10)
    with pytest.raises(ValueError, match="Unexpected output"):
        _verify_output(outside, root, 512, 512)
    local = root / "wrong_name.png"
    local.write_bytes(b"not a PNG" * 10)
    with pytest.raises(ValueError, match="Unexpected output"):
        _verify_output(local, root, 512, 512)


def test_cli_execute_without_double_consent_exits_before_cuda(monkeypatch):
    import hardware_acceptance
    def forbidden(*args, **kwargs):
        raise AssertionError("CLI bypassed explicit consent")
    monkeypatch.setattr(hardware_acceptance, "run_acceptance", forbidden)
    with pytest.raises(SystemExit) as exc:
        main(["--checkpoint", "checkpoints/mock.safetensors",
              "--prompt", "Private prompt", "--execute"])
    assert exc.value.code == 2


def test_vram_safe_8gib_trial_is_allowed_without_override(tmp_path):
    fixture_model(tmp_path)
    report = run_acceptance(
        settings(), model_root=tmp_path, inspect=True,
        gpu_inspector=gpu_report,
    )
    assert report["status"] == "gpu_probe_only"
    assert report["memory_policy"]["status"] == "conservative_trial_allowed"
    assert report["memory_policy"]["reasons"] == []
    assert report["generation"]["status"] == "not_run"


def test_low_free_vram_blocks_before_importing_or_running_any_model(tmp_path):
    fixture_model(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Torch or inference must not be called if VRAM is low")
    reading = gpu_report()
    reading["gpu"]["free_vram_bytes_at_check"] = 3 * 1024**3
    report = run_acceptance(
        settings(), model_root=tmp_path,
        execute=True, confirmed=True, gpu_inspector=lambda: reading,
        torch_loader=forbidden, runner=forbidden,
    )
    assert report["status"] == "vram_safety_blocked"
    assert "free_vram_under_4gib" in report["memory_policy"]["reasons"]
    assert report["generation"]["status"] == "not_run"


def test_high_resolution_8gib_trial_is_blocked_by_default(tmp_path):
    fixture_model(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("High resolution must be blocked before model loads")
    report = run_acceptance(
        GenerationSettings(
            checkpoint_id="checkpoints/mock.safetensors",
            prompt="High resolution fixture", width=1024, height=1024, steps=15,
        ),
        model_root=tmp_path, execute=True, confirmed=True,
        gpu_inspector=gpu_report, torch_loader=forbidden, runner=forbidden,
    )
    assert report["status"] == "vram_safety_blocked"
    assert "high_resolution_on_8gib" in report["memory_policy"]["reasons"]


def test_additional_acknowledgement_allows_attempt_but_not_success_claim(tmp_path):
    fixture_model(tmp_path)
    reading = gpu_report()
    reading["gpu"]["free_vram_bytes_at_check"] = 2 * 1024**3
    def fake_oom(*args, **kwargs):
        raise RuntimeError("CUDA out of memory")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        acknowledge_vram_risk=True,
        gpu_inspector=lambda: reading,
        torch_loader=lambda _: SimpleNamespace(cuda=MockCuda()),
        runner=fake_oom,
    )
    assert report["status"] == "generation_failed"
    assert report["memory_policy"]["status"] == "allowed_with_acknowledged_risk"
    assert report["memory_policy"]["acknowledged"] is True
    assert report["generation"]["error_category"] == "cuda_out_of_memory"
    assert any("명시적으로" in w for w in report["warnings"])


@pytest.mark.parametrize("bad_total,bad_free", [
    (8 * 1024**3, 9 * 1024**3),
    (8 * 1024**3, -1),
    (-1, 0),
    (0, 0),
    ("8589934592", 1),
    (True, 1),
])
def test_invalid_gpu_memory_values_never_authorize_inference(tmp_path, bad_total, bad_free):
    fixture_model(tmp_path)
    reading = gpu_report()
    reading["gpu"]["total_vram_bytes"] = bad_total
    reading["gpu"]["free_vram_bytes_at_check"] = bad_free
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid telemetry must not load a model")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        acknowledge_vram_risk=True,
        gpu_inspector=lambda: reading, torch_loader=forbidden, runner=forbidden,
    )
    assert report["status"] == "gpu_not_ready"
    assert report["gpu"]["status"] == "cuda_probe_error"


def test_override_never_bypasses_missing_cuda(tmp_path):
    fixture_model(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Override must not bypass missing CUDA")
    report = run_acceptance(
        settings(), model_root=tmp_path, execute=True, confirmed=True,
        acknowledge_vram_risk=True,
        gpu_inspector=lambda: {"status": "cuda_unavailable"},
        torch_loader=forbidden,
    )
    assert report["status"] == "gpu_not_ready"


def test_cli_vram_override_without_double_consent_rejected(monkeypatch):
    import hardware_acceptance
    def forbidden(*args, **kwargs):
        raise AssertionError("VRAM acknowledgement bypassed the double consent gate")
    monkeypatch.setattr(hardware_acceptance, "run_acceptance", forbidden)
    with pytest.raises(SystemExit) as err:
        main(["--checkpoint", "checkpoints/mock.safetensors",
              "--acknowledge-vram-risk"])
    assert err.value.code == 2
    with pytest.raises(SystemExit) as err:
        main(["--checkpoint", "checkpoints/mock.safetensors",
              "--prompt", "Fixture", "--execute", "--acknowledge-vram-risk"])
    assert err.value.code == 2


def test_valid_nvidia_name_retained_and_path_like_gpu_label_redacted(tmp_path):
    fixture_model(tmp_path)
    raw = gpu_report()
    good = run_acceptance(settings(), model_root=tmp_path, inspect=True,
                          gpu_inspector=lambda: raw)
    assert good["gpu"]["name"] == "Synthetic RTX 2060 SUPER"
    raw["gpu"]["name"] = r"C:\Users\private\checkpoint.safetensors"
    suspicious = run_acceptance(settings(), model_root=tmp_path, inspect=True,
                                gpu_inspector=lambda: raw)
    assert suspicious["gpu"]["name"] == "unknown"
    assert "private" not in json.dumps(suspicious)


def test_unexpected_gpu_status_payload_safely_rejected(tmp_path):
    fixture_model(tmp_path)
    report = run_acceptance(
        settings(), model_root=tmp_path, inspect=True,
        gpu_inspector=lambda: {"status": ["path", "private"]},
    )
    assert report["gpu"] == {"status": "cuda_probe_error"}
