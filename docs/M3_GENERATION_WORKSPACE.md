# M3-2 — Generation workspace and read-only results gallery

This milestone adds a **real React configuration UI** to the **이미지 생성**
(Image Generation) tab, with checkpoint selection, prompt, negative prompt,
width/height, steps, guidance, seed and a metadata-only input preflight.
The "Generate image" action remains **disabled**, since no authenticated,
packaged, owner-only GPU job execution service has been implemented.

## Capabilities

- Both the Tauri desktop and browser can display model selections:
  desktop reads the Rust-native catalog; browser requires the existing
  loopback FastAPI model-list endpoint.
- The preflight validates input ranges and a recorded SDXL family hint, and
  prominently warns that CUDA availability, model loading, config files,
  inference performance and LoRA compatibility have NOT been checked.
- Tauri's **이미지 새로고침** button reads up to four locally generated,
  recent `aiimage-<32 hex>.png` files. Rust enforces a fixed output directory,
  limited file sizes (8 MiB each), read-only PNG magic checks, and ignores
  symlinks. No path is supplied by the frontend.
- PNGs are returned as size-bounded base64 data URLs. The UI does not
  expose the Tauri asset protocol or arbitrary filesystem access.
- In development, this reads the same `outputs` directory used by the
  M3-1 CLI. In a release build, previews are read from the app-local-data
  output directory, but a packaged CLI or Python backend has **not been
  integrated**, so the gallery may be empty.
- In a normal browser, the gallery is disabled because no backend image
  retrieval API exists. We deliberately did not create a file-reading API
  on unauthenticated FastAPI.
- File previews are read on user navigation or manual refresh, not through
  continuous polling or background work. This is **not** GPU job progress.

## User workflow in a dev Tauri window

1. Import a local SDXL safetensors checkpoint in Model Management.
2. Open Image Generation; choose the checkpoint and enter parameters.
3. Run **입력 사전 검사** to check form values and recorded model family.
4. Use the separate Python CLI with `--execute` to attempt actual inference;
   see [M3-1 guide](M3_LOCAL_INFERENCE.md). It requires a compatible CUDA GPU,
   installed PyTorch/Diffusers packages and offline SDXL configuration files.
5. Click **이미지 새로고침** in the Tauri gallery to show generated PNGs.

Input validation here is **not** runtime validation. To avoid accidental
GPU execution, the current UI deliberately cannot start or cancel inference,
cannot display real progress, and does not claim completion on a preflight.

## Security and resource bounds

- No arbitrary file-path argument exposed by the new Rust command.
- Only fixed output directory and `aiimage-*.png` filenames are read.
- Each file is capped at 8 MiB; at most four previews are returned, minimizing
  IPC memory/latency. The directory scan stops after 500 entries.
- This is a display-only convenience, not a PNG content security audit.
- No downloads, model execution, authentication bypass or network requests
  are added by M3-2.

## Automated QA vs real-device QA

New Vitest tests cover the preflight and no-path IPC contract. New Rust tests
cover whitelist filters, preview caps and invalid files. GitHub Actions runs
frontend build/Vitest, Linux/Windows Python tests, and Windows Rust tests.
CI does not click a real picker, run a CUDA GPU, validate image output
quality, or measure RTX 2060 SUPER 8 GiB performance.

## Next milestone

M3-3 should introduce a Windows-only, owner-authorized job runner with a
packaged/selected Python interpreter and a secure process lifecycle,
cancellation semantics, bounded job logs, GPU OOM handling and authentic
runtime progress. The Python service must not be exposed to untrusted HTTP
requests. Actual local image generation must be tested on target hardware.
