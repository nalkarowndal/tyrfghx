"""No network, GPU, model downloads, actual weights, or torch required in CI."""
import json
import os
import struct
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from generate_sdxl import GenerationSettings, infer_sdxl, prepare_generation, run_generation


def synthetic_checkpoint(root, filename="mock.safetensors", family="stable-diffusion-xl-v1-base"):
    folder = root / "checkpoints"
    folder.mkdir(parents=True, exist_ok=True)
    metadata = json.dumps({"__metadata__": {"modelspec.architecture": family}}).encode()
    path = folder / filename
    path.write_bytes(struct.pack("<Q", len(metadata)) + metadata + b"\x00" * 16)
    return path


def local_config(root):
    config = root / "configs" / "sdxl-base-1.0"
    config.mkdir(parents=True)
    (config / "model_index.json").write_text('{"_class_name":"StableDiffusionXLPipeline"}')
    return config


def request(**overrides):
    return GenerationSettings(**{
        "checkpoint_id": "checkpoints/mock.safetensors",
        "prompt": "An original watercolor forest",
        **overrides,
    })


def test_dry_run_preflight_never_imports_gpu_modules(tmp_path, monkeypatch):
    synthetic_checkpoint(tmp_path)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    path, config, plan = prepare_generation(request(), tmp_path)
    assert path.name == "mock.safetensors"
    assert config.name == "sdxl-base-1.0"
    assert plan.recorded_family == "sdxl"
    assert not plan.config_found
    assert "HF_HUB_OFFLINE" not in os.environ


@pytest.mark.parametrize("changes", [
    {"width": 513}, {"height": 2048}, {"steps": 0}, {"steps": 60},
    {"guidance_scale": 0}, {"guidance_scale": 20},
    {"seed": -1}, {"seed": 2**32}, {"prompt": ""}, {"prompt": "x" * 2001},
    {"checkpoint_id": "../model.safetensors"},
])
def test_bad_parameters_rejected(changes):
    with pytest.raises(ValueError):
        request(**changes)


def test_reject_unsupported_family_and_legacy(tmp_path):
    synthetic_checkpoint(tmp_path, family="stable-diffusion-v1")
    with pytest.raises(ValueError, match="SDXL"):
        prepare_generation(request(), tmp_path)
    (tmp_path / "checkpoints" / "legacy.ckpt").write_bytes(b"not safetensors")
    with pytest.raises(ValueError):
        prepare_generation(request(checkpoint_id="checkpoints/legacy.ckpt"), tmp_path)


def test_reject_corrupt_header(tmp_path):
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    (folder / "mock.safetensors").write_bytes(b"broken")
    with pytest.raises(ValueError):
        prepare_generation(request(), tmp_path)


def test_no_config_means_never_start_inference(tmp_path):
    synthetic_checkpoint(tmp_path)
    with pytest.raises(ValueError, match="config missing"):
        run_generation(request(), model_root=tmp_path, output_root=tmp_path / "outputs")
    assert not (tmp_path / "outputs").exists()


class FakeImage:
    def save(self, buffer, format):
        assert format == "PNG"
        buffer.write(b"synthetic test image")


class FakePipeline:
    loaded = None
    offloaded = False
    vae_sliced = False
    called = None

    @classmethod
    def from_single_file(cls, path, **kwargs):
        cls.loaded = (path, kwargs)
        return cls()

    def enable_model_cpu_offload(self):
        type(self).offloaded = True

    def enable_vae_slicing(self):
        type(self).vae_sliced = True

    def __call__(self, **kwargs):
        type(self).called = kwargs
        return SimpleNamespace(images=[FakeImage()])


class FakeGenerator:
    def __init__(self, device):
        assert device == "cpu"

    def manual_seed(self, seed):
        self.seed = seed
        return self


class FakeTorch:
    float16 = object()
    Generator = FakeGenerator
    inference_mode = staticmethod(nullcontext)
    cuda = SimpleNamespace(is_available=lambda: True)


def test_explicit_execute_with_stub_uses_offload_and_local_only(tmp_path, monkeypatch):
    synthetic_checkpoint(tmp_path)
    local_config(tmp_path)
    out = tmp_path / "outputs"
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    result = run_generation(request(seed=123), model_root=tmp_path, output_root=out,
                            torch_module=FakeTorch(), pipeline_type=FakePipeline)
    assert result.is_file()
    assert result.read_bytes() == b"synthetic test image"
    assert FakePipeline.loaded[1]["local_files_only"] is True
    assert FakePipeline.loaded[1]["config"].endswith("sdxl-base-1.0")
    assert FakePipeline.offloaded is True
    assert FakePipeline.called["num_images_per_prompt"] == 1
    assert FakePipeline.called["generator"].seed == 123
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_gpu_not_available_rejects_before_loading(tmp_path):
    synthetic_checkpoint(tmp_path)
    local_config(tmp_path)
    device = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(RuntimeError, match="CUDA"):
        run_generation(request(), model_root=tmp_path, output_root=tmp_path / "outputs",
                       torch_module=device, pipeline_type=FakePipeline)
    assert not (tmp_path / "outputs").exists()


def test_config_symlink_rejected(tmp_path):
    synthetic_checkpoint(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (external / "model_index.json").write_text("{}")
    configs = tmp_path / "configs"
    configs.mkdir()
    try:
        (configs / "sdxl-base-1.0").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError, match="symlink"):
        prepare_generation(request(), tmp_path)


def test_output_not_overwritten(tmp_path):
    from generate_sdxl import save_image
    output = tmp_path / "outputs"
    output.mkdir()
    sentinel = output / "important.png"
    sentinel.write_bytes(b"keep")
    result = save_image(FakeImage(), output)
    assert result != sentinel
    assert sentinel.read_bytes() == b"keep"
