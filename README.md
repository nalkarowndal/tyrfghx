# aiimage

Local-first AI image/video creative studio for Windows. Built incrementally
with React/TypeScript/Vite (UI), Tauri 2 (desktop shell), and FastAPI (local API).

> **Current milestone: M2-5 (offline Tauri model browsing preview).**
> This is **not yet an operational AI image generator**. GPU inference (M3),
> RTX 2060 SUPER 8GB performance verification, packaged Tauri runtime, and
> actual native window testing remain outstanding.

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
- [M1 developer environment](docs/DEVELOPMENT.md)
- Backend tests: `cd backend && python -m pytest -q`
- Frontend: `npm run build && npm test`
- GitHub: `.github/workflows/ci.yml`

M10 is reserved for a Krea-inspired canvas/editor workflow, **not** multi-character
generation. ComfyUI remains an optional future engine adapter.
