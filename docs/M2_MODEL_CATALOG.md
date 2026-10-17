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

## M2-3 — Local file import and recorded SHA-256

This increment adds a **local command-line file selector** (Tkinter native
file dialog on a desktop Python installation). It is not a Tauri in-app picker.

From the `backend` directory:

```powershell
python model_import.py --category checkpoints
python model_import.py --category loras --source "C:\\Downloads\\style.safetensors"
python model_import.py --category vae --source "C:\\Downloads\\vae.safetensors" --expected-sha256 "<64-char trusted hash>"
python model_import.py --category checkpoints --verify "checkpoints/my-model.safetensors"
```

- Import is explicit and local, copies source without editing the original.
- `.safetensors` header is checked before copying; `.ckpt` is refused.
- Uses streaming SHA-256 with fixed 4 MiB buffers, bounded by 64 GiB per file.
- Stage-and-hardlink ensures a final filename is never silently overwritten;
  this requires local filesystem hard-link support (NTFS is supported).
- Optional `--expected-sha256` rejects a copy that does not match a separately
  obtained trusted digest.
- Writes `models/integrity.json` with checksum, file size, and file mtime.
  Do not check model files or integrity registry into Git.
- The model page shows **recorded checksum** and snapshot freshness based on
  size/mtime, not a live cryptographic verification. A malicious or same-size
  modification may not change these indicators.
- `--verify` recomputes current SHA-256 against the recorded hash; it
  **does not rewrite or trust** a corrupted record. Return code 0 is a match,
  code 2 is mismatch or not recorded.
- Identical recorded hashes are labeled **potential duplicates** only.
- The HTTP server still has no model-file upload, delete, or arbitrary file
  read/hash endpoint. Actual Tauri-integrated file picking remains future work.

QA includes synthetic fixture imports, hash mismatch, no-overwrite behavior,
file mutation, rejected unsafe formats/links, and corrupt-manifest handling.
No GPU/model execution is performed.

## M2-4 — native Tauri file selection (development preview)

The desktop-only **파일 선택 후 가져오기** button is now wired to a
registered Tauri v2 Rust command, `import_local_model`. The webview passes
**only** the category (`checkpoints`, `loras`, or `vae`).
The native OS dialog obtains the actual source path entirely inside Rust.
Canceling the dialog returns no result and makes no filesystem changes.

Rust copies a local `.safetensors` model into the category folder, checks a
bounded JSON header, streams a SHA-256 checksum, rejects collisions, and writes
the same `models/integrity.json` schema used by the Python CLI. Model weights
are never loaded into torch, nor sent through an HTTP upload endpoint.

- Development (`npm run tauri dev`): imports to `<repo>/models`, shared with
  the separately running local FastAPI API. Click **목록 새로고침** if needed.
- Release builds: import to Tauri's application-local-data `models` folder.
  Packaging/auto-start of the Python service is **not implemented yet**;
  production imports cannot appear in the UI catalog until backend storage
  configuration is unified in a later milestone.
- Browser-only `npm run dev`: the import button is disabled; use the existing
  local Python CLI importer.
- Tauri's dialog is available through the Rust plugin, not an unrestricted
  JavaScript filesystem plugin; there are no additional webview FS privileges.
- Confirmed test coverage in CI must include desktop Rust build/tests on
  Windows, not merely frontend `npm run build`.
- Actual GUI picker, Windows runtime behavior, antivirus interaction,
  filesystem permissions and packaging remain subject to user-device QA.

The preview is intentionally not a complete model-manager release.

## M2-5 — offline native model catalog (Tauri)

Tauri now supports read-only `list_local_models` with **no source-path
argument**. This command discovers only direct files within the same root used
by the native importer: `models/checkpoints`, `models/loras`, `models/vae`.

The native command reads at most 1 MiB from each safetensors JSON header and
up to 1 MiB per annotations/integrity registry; it ignores symlinked files.
No weights are deserialized or transferred through frontend IPC.

- In a Tauri window, browsing and approximate checkpoint/LoRA family checks
  work even if the Python HTTP backend is stopped.
- In a plain web browser, the existing local Python API remains necessary.
- In a development build, Tauri uses the repo-local `models` root.
- In a release build, Tauri uses `app_local_data_dir()/models` both for
  import and listing. Python auto-start and inference are **not** implemented;
  no actual AI generation is available.
- Family match is a **metadata suggestion**, never a promise that a model or
  LoRA can load or produce images. Snapshot freshness is a file size/mtime
  comparison, not live cryptographic verification.
- Tauri code is verified by Windows `cargo test --lib` in CI; a real
  interactive file-picker/UI test on Windows remains separate work.

Further tasks: integrate a signed, packaged and user-controlled Python
inference backend, align its release-time storage root, secure local service
authentication, exercise end-to-end UI tests, and validate supported model
architectures on RTX 2060 SUPER 8GB before making generation features active.
