# M3-20 — Independent local PNG integrity verification

M3-20 adds an **optional, explicit, read-only local PNG integrity check**
to the M3-19 hardware evidence review tool. It is intended for the
owner's Windows machine after a real SDXL generation. CI uses
synthetic, known-good PNG fixtures, **not the owner's RTX 2060 SUPER**.

## Running

First produce an M3-10 generation report and an M3-18 NVIDIA
system-memory observation report using their existing documented
procedures. Retain the **actual** generated PNG in the app's local
output directory; do not rename it or modify the bytes after the
generation report was created.

From a terminal in the repository root, with the generated output
directory chosen explicitly by the operator:

~~~powershell
.\.venv\Scripts\python.exe backend\hardware_evidence_review.py --generation-json ".\generation-report.json" --gpu-memory-json ".\vram-report.json" --output-root ".\outputs" --confirm-review
~~~

`--output-root` is **optional** for backward compatibility.
Without it the report's new `independent_png.verification` is
`not_requested`, because merely reading a claimed SHA-256 from JSON
is not actual independent file verification.

With `--output-root` the tool reads only **one fixed, source-claimed
`aiimage-<32 lowercase hex>.png` file** from the owner-selected
directory, never enumerates arbitrary directories, opens models,
loads a GPU, runs subprocesses, uploads content, or creates output
artifacts. A generation report that does not claim
`generated_png_decoded` is refused.

## What is checked from real PNG bytes

- Existing regular file, no symlink root or PNG file, safe basename and
  expected local directory, maximum 8MiB input bytes.
- Exact byte count and SHA-256 digest equal to the M3-10 generator's
  recorded claims. The expected digest is never treated as trustworthy
  without reading and hashing the actual bytes independently.
- Valid PNG signature and complete bounded chunk sequence.
- Valid per-chunk CRC-32, IHDR structure, IDAT and terminal IEND with
  no trailing data. Unknown critical chunks, animation/APNG, repeated
  IHDR and interrupted IDAT sequences are refused.
- **8-bit, noninterlaced RGB or RGBA** images (the intended local SDXL
  PNG export); exact width/height within 1024 pixels per edge.
- Bounded zlib decompression of IDAT, exact scanline byte count,
  decompression stream completion and reconstructed per-pixel scanline
  filters 0–4. No unbounded decompression or imports of optional
  Torch/Diffusers/CUDA/Pillow dependencies.

A successful optional check returns
`png_crc_zlib_filters_sha256_and_dimensions_verified` along with
independently checked dimensions, byte length and digest. A mismatch
returns only a fixed safe error code and does not echo any image or
input-file path. The independent check operates on one bounded local
byte buffer to reduce file-changed-between-reads ambiguity.

## Important interpretation

This is evidence of **file structure, integrity and decoded scanlines**,
not proof of the inference runtime, prompt fidelity, screenshot
appearance, aesthetics, color accuracy or whether an image was actually
created by CUDA on the user's PC. A user could craft synthetic or
tampered JSON plus a matching PNG; that does not prove hardware
provenance. The M3-19 status remains only
`evidence_available_for_manual_review`. The operator still needs to
open the PNG in a trusted viewer and examine artistic output,
Tauri interaction, cancellation, process cleanup, and GPU memory.

Every previous `manual_checks` item remains `not_tested`,
including app-specific CUDA VRAM reclamation, network isolation, and
whether the generation/VRAM reports are from the same session.

The verifier accepts only 8-bit RGB/RGBA noninterlaced PNGs by design.
Other valid PNG encodings will be rejected rather than silently
treated as equivalent SDXL outputs. This strictness is intentional
for the current local generation pipeline, not a generic image reader.

## Synthetic CI tests

Python tests construct actual zlib-compressed RGB and RGBA PNG files,
including all five PNG row filters, and verify CRC, dimensions,
hash/digest comparison and M3-19 report integration. Malformed,
truncated, appended, symlinked, manipulated-claim and wrong-color
fixtures must be rejected. No test accesses CUDA or a Windows NVIDIA
device.

Source references:
- PNG specification: https://www.w3.org/TR/png-3/
- Pillow `verify()` vs `load()` behavior: https://pillow.readthedocs.io/en/stable/reference/Image.html
- M3_HARDWARE_EVIDENCE_REVIEW.md
