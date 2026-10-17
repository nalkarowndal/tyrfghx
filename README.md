# aiimage

Local-first AI image/video creative studio for Windows. Built incrementally
with React/TypeScript/Vite (UI), Tauri 2 (desktop shell), and FastAPI (local API).

> **Current milestone: M3-2 (image settings workspace + offline output previews).**
> M3-1 adds source code for an **opt-in local SDXL generation attempt**. A real
> GPU image has NOT been generated or benchmarked by this development workflow.
> The actual Tauri image-generation button remains disabled; packaged backend
> integration, driver/device validation, and native GUI testing are outstanding.

## What works in the codebase

- Local read-only catalog of checkpoints, LoRA and VAE safetensors files.
- Bounded header metadata reader and conservative, non-executing family hints.
- User-defined metadata via local CLI: display name, family, notes and license.
- LoRA–checkpoint family comparison (metadata *suggestion*, not loading proof).
- **Explicit local import via CLI** with a Tkinter desktop file picker, or
  `--source` for a path you select. Imports keep the source intact.
- **Native Tauri desktop model catalog:** lists local models even when the
  Python API is not running, including bounded safetensors header metadata and
  registration-time integrity snapshot hints. It has no filesystem path inputs.
- **Native Tauri desktop import button:** invokes a Rust file picker and copies
  locally. It accepts only a model category from the webview, never a path.
  The browser-only version disables this button.
- Streaming SHA-256 and optional trusted expected checksum, collision prevention,
  and locally recorded integrity snapshots.
- Locally recompute a model checksum with `--verify`. UI only displays
  recorded checksum and size/mtime snapshot changes, not live verification.
- Linux and Windows Python tests and frontend tests in GitHub Actions;
  M2-4 also adds Windows Rust build/unit-test CI.

## Generation workspace (M3-2)

Open **이미지 생성** in the React/Tauri interface to select a checkpoint,
enter prompts and seed/size settings, and run a **metadata-only input preflight**.
This preflight is not a real CUDA/image test. The generate action is disabled.

The Tauri view can preview up to four of the latest local PNG images generated
by the separate CLI. Browser builds cannot read local output files; no generic
filesystem API is added. See [M3-2 generation workspace](docs/M3_GENERATION_WORKSPACE.md).

## Experimental SDXL image generation (M3-1)

On a machine with CUDA-enabled PyTorch, additional optional dependencies,
an SDXL safetensors checkpoint and its offline pipeline configuration, run:

```powershell
python backend/generate_sdxl.py --checkpoint "checkpoints/model.safetensors" --prompt "An original watercolor landscape"
```

This is **dry run only**. To attempt one real local image, add `--execute`.
No model or config is downloaded automatically. Only checkpoint files under
the repository's `models/checkpoints` root are accepted. Images, if
successfully generated, go to `outputs/` and do not overwrite existing files.

See [M3 local inference setup, limits and GPU QA](docs/M3_LOCAL_INFERENCE.md).
This CLI is not yet connected to the web/Tauri UI.

## Development quick start

Prerequisites: Python 3.12+, Node.js 22+, and Rust/Windows C++ Build Tools +
WebView2 when developing the Tauri desktop shell.

In terminal A:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

In terminal B (repository root):

```powershell
npm install
npm run dev
```

Optional Tauri desktop dev window after Rust setup: `npm run tauri dev`.
The FastAPI backend is **not bundled or auto-started yet**.

## Local file import

In the `backend` folder, using a Python desktop installation with Tkinter:

```powershell
python model_import.py --category checkpoints
python model_import.py --category loras --source "C:\Downloads\lora.safetensors"
python model_import.py --category checkpoints --verify "checkpoints/my-model.safetensors"
```

Accepted categories: `checkpoints`, `loras`, `vae`.
The CLI chooser is independent from the newer **Tauri-native model import button**.
During Tauri development both use the repository \`models\` directory.
Release builds import and browse from the same app-local-data \`models\` directory
using Tauri. Python API auto-start, model inference, and packaged backend integration
are not implemented yet.
Safetensors only; legacy CKPT is deliberately never imported or loaded.
Model files and local integrity registries are ignored by Git.

## Docs and verification

- [M2 model catalog, metadata, import and integrity](docs/M2_MODEL_CATALOG.md)
- [M3 offline SDXL CLI and hardware-validation guide](docs/M3_LOCAL_INFERENCE.md)
- [M1 developer environment](docs/DEVELOPMENT.md)
- Backend tests: `cd backend && python -m pytest -q`
- Frontend: `npm run build && npm test`
- GitHub: `.github/workflows/ci.yml`

M10 is reserved for a Krea-inspired canvas/editor workflow, **not** multi-character
generation. ComfyUI remains an optional future engine adapter.
