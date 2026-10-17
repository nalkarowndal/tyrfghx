# M3-1 — Local SDXL inference CLI (experimental)

This is the **first executable local image-generation code**, not a packaged
product, a GPU QA result, or a universal Anima/Illustrious compatibility layer.
Only single-file SDXL safetensors checkpoints with recognized SDXL metadata are
eligible. Manual family overrides are *unverified hints*, never a guarantee.

## Why a CLI first?

The current FastAPI service has no authentication or owner-only execution
permission protocol. Opening a POST endpoint to arbitrary local GPU jobs now
would be unsafe. M3-1 therefore runs ONLY after an explicit user-initiated
`--execute` flag in a local terminal. The browser/Tauri generation button
remains disabled. No network or weight downloads are initiated by this CLI.

## Prepare on Windows / RTX 2060 SUPER 8 GB

1. Use Python 3.12 in a virtual environment. Install the existing base
   backend requirements: `pip install -r backend/requirements.txt`.
2. Install a **CUDA-enabled PyTorch build** using the official selector at
   https://pytorch.org/get-started/locally/ . Confirm
   `python -c "import torch; print(torch.cuda.is_available())"` prints `True`.
3. Install optional packages: `pip install -r backend/requirements-inference.txt`.
   These may be large, and installing them is an explicit local decision.
4. Import an SDXL `.safetensors` checkpoint to `models/checkpoints/` using
   the existing M2 file-import workflow. The file must be legally usable.
5. Prepare the **local SDXL pipeline configuration** in
   `models/configs/sdxl-base-1.0/` with `model_index.json` and all supporting
   config/tokenizer files. These must be downloaded or copied independently
   from trusted/authorized sources before running the CLI. The CLI **never**
   downloads configurations or weights automatically. Official guidance:
   https://huggingface.co/docs/diffusers/en/using-diffusers/other-formats
6. The checkpoint may be a derivative: matching family metadata alone does not
   prove that Diffusers can interpret its tensors or that it works in 8 GiB.

## Example commands

From the repository root:

```powershell
python backend/generate_sdxl.py --checkpoint "checkpoints/model.safetensors" --prompt "A peaceful watercolor landscape"
```

This is **only a dry run**; it prints validated model hints and whether the
local config is present. It imports neither Torch nor Diffusers and generates
no image. To attempt real local inference, add **--execute** explicitly:

```powershell
python backend/generate_sdxl.py --checkpoint "checkpoints/model.safetensors" --prompt "A peaceful watercolor landscape" --width 768 --height 768 --steps 20 --seed 42 --execute
```

With a compatible installation/GPU/model/config, output is written exclusively
to the repository's `outputs/aiimage-<random>.png` (never overwrites existing
files). The CLI prints a local output path. It does not run an image safety
classifier or verify a model's license; the user must check model terms.

## Inference behavior and limits

- Offline is forced before heavy imports via `HF_HUB_OFFLINE=1`, and
  `local_files_only=True` is passed to the pipeline.
- `StableDiffusionXLPipeline.from_single_file` loads the selected local path
  with the supplied local config; PyTorch float16, CPU model offload, optional
  VAE slicing, a CPU random generator, and one image per invocation.
- Defaults are 768×768, 20 steps, CFG 7 and seed 42. Allowed dimensions
  512–1024 in steps of 64, steps 1–40, guidance 1–12, and one image.
- Only CUDA is supported by this preview, no silent CPU fallback. No LoRA,
  ControlNet, img2img, inpainting, video, queued jobs, or ComfyUI yet.
- Even with CPU offload an 8GB card may run out of memory or be too slow;
  the actual behavior has **not been measured** on RTX 2060 SUPER.
- In CI, tests use synthetic safetensors headers and injected fake pipeline
  objects. Neither a GPU image nor a model weight is loaded in CI.
- Release Tauri's model root is app-local-data; this CLI currently uses the
  repository-local `models` folder. Packaged Python sidecar and shared
  production runtime storage are future integration steps.

## QA

```powershell
cd backend
python -m pytest -q test_generation.py
```

After real device testing, record driver version, PyTorch CUDA build, GPU name,
VRAM allocation, checkpoint source/license, config source, duration, resolution,
image file SHA-256, and actual error logs before labeling M3 hardware verified.
