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


## M2-2: local metadata registration and cautious compatibility comparison

From `backend`, after placing a real `.safetensors` file in an approved
model directory, optionally annotate it with:

```powershell
python model_register.py "loras/style.safetensors" --name "My Style" --family sdxl --license "Check model card" --notes "Artist supplied model"
```

This saves locally to `models/annotations.json`. No weight file is modified.
The CLI rejects paths outside the predefined category folders, traversal,
missing files, and symlinks. The registry is not uploaded to GitHub.
The `GET /api/models/compatibility` endpoint is **read-only**. This milestone
does not expose an unprotected HTTP write endpoint or a file upload endpoint.

The **모델 관리** page can filter by name/category and choose a checkpoint and
LoRA for a preliminary comparison. It reports four relevant conditions:
- same declared/inferred family: *possible_match*, **not** proven compatibility;
- differing family: *family_mismatch* warning;
- unknown metadata: *unknown*;
- invalid safetensors/legacy CKPT: *blocked*.

The architecture family is inferred only from a narrow set of known SAI
ModelSpec and trainer labels. Anima, Illustrious and other derivative filenames
are never automatically assumed to be SDXL. A manual family override is
displayed as **user supplied**. GPU behavior, model loading, memory requirement,
LoRA tensor/key compatibility, licensing compliance, and inference are not
validated. WAI-Illustrious / Anima support remains future engine work.

Sources:
- https://github.com/Stability-AI/ModelSpec
- https://huggingface.co/docs/diffusers/en/api/loaders/single_file

Tests: `cd backend && python -m pytest -q`, `npm run build`, `npm test`.
Windows desktop use, GPU tests, and visual UI testing are still pending.
