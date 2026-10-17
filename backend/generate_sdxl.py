"""M3-1: opt-in, offline SDXL single-file inference CLI (no HTTP execution API).

Standard dry run NEVER imports torch, diffusers, accesses the network, or
allocates GPU memory. Use --execute deliberately on the owner's machine.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from model_catalog import MODEL_ROOT, scan_models
from model_integrity import model_file

CONFIG_RELATIVE = Path("configs") / "sdxl-base-1.0"
OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs"
MAX_PNG_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class GenerationSettings:
    checkpoint_id: str
    prompt: str
    negative_prompt: str = ""
    width: int = 768
    height: int = 768
    steps: int = 20
    guidance_scale: float = 7.0
    seed: int = 42

    def __post_init__(self) -> None:
        if not self.checkpoint_id.startswith("checkpoints/"):
            raise ValueError("Only registered checkpoint IDs may be used.")
        if not self.prompt.strip() or len(self.prompt) > 2000:
            raise ValueError("Prompt must contain 1–2000 characters.")
        if len(self.negative_prompt) > 2000:
            raise ValueError("Negative prompt exceeds 2000 characters.")
        for dim in (self.width, self.height):
            if not 512 <= dim <= 1024 or dim % 64:
                raise ValueError("Width and height must be multiples of 64 from 512 to 1024.")
        if not 1 <= self.steps <= 40:
            raise ValueError("Steps must be between 1 and 40.")
        if not 1.0 <= self.guidance_scale <= 12.0:
            raise ValueError("Guidance must be between 1 and 12.")
        if not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("Seed out of range.")


@dataclass(frozen=True)
class GenerationPlan:
    checkpoint_id: str
    recorded_family: str
    family_source: str
    config_found: bool
    offline_only: bool = True
    engine: str = "sdxl_diffusers_cpu_offload_preview"


def prepare_generation(settings: GenerationSettings, model_root: Path = MODEL_ROOT) -> tuple[Path, Path, GenerationPlan]:
    """Validate the model WITHOUT calling torch or any model deserializer.

    Family metadata is merely an untrusted hint; it cannot prove compatibility.
    """
    path = model_file(model_root, settings.checkpoint_id)
    records = scan_models(model_root)
    found = next((item for item in records if item.id == settings.checkpoint_id), None)
    if found is None or found.file_format != "safetensors" or found.validation != "metadata_only":
        raise ValueError("A valid safetensors checkpoint is required.")
    if found.family != "sdxl":
        raise ValueError("Only an explicitly identified SDXL-family checkpoint is supported in M3-1.")
    config = model_root / CONFIG_RELATIVE
    if model_root.is_symlink() or (model_root / "configs").is_symlink() or config.is_symlink():
        raise ValueError("Config symlinks are not permitted.")
    exists = config.is_dir() and (config / "model_index.json").is_file() and not (config / "model_index.json").is_symlink()
    return path, config, GenerationPlan(
        checkpoint_id=found.id,
        recorded_family=found.family,
        family_source=found.family_source,
        config_found=exists,
    )


def infer_sdxl(path: Path, config: Path, settings: GenerationSettings, *,
               torch_module=None, pipeline_type=None):
    """Explicit heavy inference; dependency injection permits CPU-only mock tests."""
    # Offline mode is set BEFORE any lazy imports to prevent implicit Hub access.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    if torch_module is None:
        import torch as torch_module
    if pipeline_type is None:
        from diffusers import StableDiffusionXLPipeline as pipeline_type
    if not torch_module.cuda.is_available():
        raise RuntimeError("A working CUDA GPU and matching CUDA-enabled PyTorch build are required.")
    pipeline = pipeline_type.from_single_file(
        str(path), config=str(config), local_files_only=True,
        dtype=torch_module.float16,
    )
    # Do NOT move the entire pipeline to CUDA: 8GB devices benefit from offload.
    pipeline.enable_model_cpu_offload()
    if hasattr(pipeline, "enable_vae_slicing"):
        pipeline.enable_vae_slicing()
    random_generator = torch_module.Generator(device="cpu").manual_seed(settings.seed)
    with torch_module.inference_mode():
        output = pipeline(
            prompt=settings.prompt,
            negative_prompt=settings.negative_prompt,
            width=settings.width, height=settings.height,
            num_inference_steps=settings.steps,
            guidance_scale=settings.guidance_scale,
            generator=random_generator,
            num_images_per_prompt=1,
        )
    if not getattr(output, "images", None):
        raise RuntimeError("The inference pipeline did not return an image.")
    return output.images[0]


def save_image(image, output_root: Path = OUTPUT_ROOT) -> Path:
    """Write a single image to the fixed local outputs folder, never overwriting."""
    if output_root.is_symlink():
        raise ValueError("Symlink output directories are blocked.")
    output_root.mkdir(parents=True, exist_ok=True)
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("Unsafe output directory.")
    content = io.BytesIO()
    image.save(content, format="PNG")
    payload = content.getvalue()
    if not payload or len(payload) > MAX_PNG_BYTES:
        raise ValueError("Generated PNG is empty or exceeds the output size limit.")
    destination = output_root / f"aiimage-{uuid.uuid4().hex}.png"
    # Exclusive mode avoids silently overwriting a user's existing output.
    with destination.open("xb") as file:
        file.write(payload)
    return destination


def run_generation(settings: GenerationSettings, *, model_root: Path = MODEL_ROOT,
                   output_root: Path = OUTPUT_ROOT, torch_module=None, pipeline_type=None) -> Path:
    path, config, plan = prepare_generation(settings, model_root)
    if not plan.config_found:
        raise ValueError("Local SDXL config missing: models/configs/sdxl-base-1.0/model_index.json")
    image = infer_sdxl(path, config, settings, torch_module=torch_module, pipeline_type=pipeline_type)
    return save_image(image, output_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M3-1 offline SDXL preview; dry run by default.")
    parser.add_argument("--checkpoint", required=True, help="E.g. checkpoints/model.safetensors")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--guidance", type=float, default=7.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--execute", action="store_true", help="Actually load checkpoint and run CUDA inference.")
    args = parser.parse_args(argv)
    try:
        settings = GenerationSettings(
            checkpoint_id=args.checkpoint, prompt=args.prompt,
            negative_prompt=args.negative_prompt, width=args.width,
            height=args.height, steps=args.steps, guidance_scale=args.guidance,
            seed=args.seed,
        )
        _, _, plan = prepare_generation(settings)
        if not args.execute:
            print(json.dumps({
                "mode": "dry_run", "plan": asdict(plan), "settings": asdict(settings),
                "warning": "This does not test model loading, GPU memory, or generation.",
            }, ensure_ascii=False, indent=2))
            return 0
        result = run_generation(settings)
        print(json.dumps({"mode": "generated_unverified", "output": str(result),
                          "seed": settings.seed}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(2, f"aiimage M3-1: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
