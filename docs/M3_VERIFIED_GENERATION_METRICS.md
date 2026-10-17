# M3-8 — Locally verified generation metrics (Windows debug only)

M3-8 bridges the existing **opt-in SDXL CLI measurement mode** to the
Tauri image generation workspace. This is a code and automated-test
milestone, NOT evidence of a successful RTX 2060 SUPER image.

## What changed

A user explicitly consents to **GPU 생성 시작** in the Windows Tauri DEBUG
app. The existing fixed, locally installed interpreter invokes
`backend/generate_sdxl.py` with **`--execute --metrics`**. No model is
downloaded. Browser, release, and unauthenticated HTTP execution are not
enabled.

The Python CLI may report the elapsed inference duration including model
loading, output PNG SHA-256, and (when available) PyTorch CUDA allocator
peak allocated/reserved bytes. The Rust job supervisor captures stdout
concurrently with stderr, **drains it to EOF** to prevent subprocess
deadlocks, but retains at most 16KiB + 1 byte. Any larger output is rejected
rather than passed to the user.

On *normal child exit* with a successful exit code and completed
process-group cleanup, Rust validates a strict JSON format:

- Mode must indicate a generation attempt and the reported seed must match
  the request.
- The only accepted output is an existing `aiimage-<32 hex>.png` in the
  repository's **fixed `outputs` directory**. Other paths, path traversal,
  symlinks, unexpected JSON keys and oversized reports fail.
- PNG must have a valid signature, be within the file-size bound (32MiB),
  and have the exact SHA-256 digest reported by Python. Rust independently
  streams the file and hashes its bytes.
- Duration must be finite and bounded. CUDA allocator measurements are
  optional and sanity-checked; unavailable values display as **미측정**.
- Only the sanitized file **name**, SHA-256, seed, duration and numeric
  metrics are sent to the frontend. The absolute file path and Python raw
  stdout/stderr are not exposed.

A malformed result or mismatched checksum turns a nominal Python
success into a **failed verification** state, rather than silently reporting
success.

## How to use

1. Install a compatible CUDA PyTorch build and optional inference
   dependencies in `<repo>/.venv/Scripts/python.exe`.
2. Add a legally usable SDXL safetensors checkpoint and offline SDXL
   pipeline configuration in the expected local `models` folders.
3. In Windows `npm run tauri dev`, open **이미지 생성**.
4. Use **GPU 진단 실행** first to inspect the local CUDA environment.
5. Choose the checkpoint, enter a prompt, check consent, and explicitly
   start one generation job.
6. After a reported successful exit, inspect the **결과 파일 검증 완료**
   panel, open/inspect the PNG in the gallery, and record the measured
   duration/peak allocated/reserved bytes and output checksum.
7. Independently inspect GPU memory using Windows Task Manager or
   `nvidia-smi` and assess image quality.

## Important interpretation

- **PNG signature + hash verification only proves stored-file consistency**.
  It does not decode every PNG chunk or prove semantic correctness,
  quality, prompt adherence, successful CUDA execution, or whether an image
  was generated on the expected physical GPU.
- PyTorch allocator peaks are **not full VRAM consumption** and exclude
  driver usage and other applications.
- Runtime duration is the value measured by the Python process around its
  explicit image generation call. It does not include OS process startup,
  and is not a progress percentage.
- GPU out-of-memory conditions, missing model config, or startup exceptions
  remain failures and do not produce fake metrics.
- In rare cases third-party libraries write unrelated data to stdout;
  the strict JSON parser rejects such output. This is an intentional
  fail-closed behavior for the preview.
- Only Windows **DEBUG** builds expose the generation job. Packaging,
  model compatibility across Anima/Illustrious, external subprocess
  supervision edge cases, device-specific speed, and real GUI QA remain
  unfinished.

## Automated QA

GitHub Windows Rust tests verify parsing, rejected external paths,
duplicate/unrecognized JSON keys, digest mismatch, fake PNG headers,
missing allocator measurement, and bounded stdout draining.
Vitest tests validate the typed IPC result and browser guards.
Python CI keeps using synthetic checkpoints/mock CUDA and creates no
genuine diffusion images.

**Actual Windows hardware validation must still be performed on the
user's target RTX 2060 SUPER 8GB machine.** Record the precise CUDA,
driver and package versions, GPU name, model origin/license, image file
hash, measured runtime, peak memory and screenshot/visual review.
