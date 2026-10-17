# M2 — Local model catalog (initial increment)

This is an **inventory**, not a GPU inference engine or model compatibility
certificate. Scanning never downloads, imports, deserializes, or executes weights.

## Windows setup

Create these folders at repository root:

```powershell
mkdir models\checkpoints
mkdir models\loras
mkdir models\vae
```

Place models directly inside the matching folder (for example,
`models/checkpoints/illustration.safetensors`). Open the **모델 관리**
(Model Management) view and click **목록 새로고침** (Refresh).

Files are never copied, moved, loaded into GPU, or deleted by the catalog.

## File / metadata policy

- Recognizes `.safetensors` and legacy `.ckpt` filenames in predefined folders.
- Safetensors: reads at most 1 MiB of JSON header for optional reported
  architecture. This reported value is untrusted metadata, **not verified compatibility**.
- CKPT: included in inventory with blocked-legacy warning; never passed to
  torch/pickle loaders.
- Files with invalid safetensors headers remain visible, marked invalid.
- Symlink files and folders are ignored; API returns relative IDs, no host paths.
- Models' sizes are disk sizes, **not** VRAM estimates.
- WAI-Illustrious, Anima, other checkpoints and LoRAs require per-model
  pipeline and compatibility checks in later milestones.

## Verification

Backend: `cd backend && python -m pytest -q`

Frontend: `npm install && npm run build && npm test`

CI tests are mock/file-fixture checks. They cannot demonstrate local Windows
desktop operation, actual model loading, GPU compatibility, or image generation.

## Next M2 increments

Add explicit registration and storage-root selection with safe authorization,
content hashes on demand, backend model compatibility adapters, and dedicated
LoRA/base-model matching. Maintain explicit user consent for downloads, and
introduce GPU inference only in M3.
