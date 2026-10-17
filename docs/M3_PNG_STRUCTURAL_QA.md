# M3-9 — PNG structural QA before reporting generation success

This milestone tightens the Windows Tauri DEBUG-only inference result
verification built in M3-8. The code now **decodes a PNG frame** using the
Rust `png` crate before treating Python's exit-zero and matching SHA-256
as evidence that an image file was successfully saved.

## Validation pipeline

1. The existing fixed offline Python SDXL CLI runs ONLY when the user
   explicitly approves execution on Windows Tauri development builds.
   Production Tauri and web builds still do not offer GPU execution.
2. Python saves a new non-overwriting `aiimage-<32 hex>.png` inside the
   fixed `outputs` folder and reports a SHA-256 and optional allocator metrics.
3. Rust checks the allowlisted JSON output, seed, canonical output path,
   filename, non-symlink file, byte size, PNG signature, and independently
   calculates the file's SHA-256.
4. Rust decodes PNG pixel data with `png::Decoder::new_with_limits`. A PNG
   header alone or correctly hashed nonsense bytes **do not** count as a
   successfully saved image.
5. The PNG must be non-animated and have positive dimensions no larger
   than 1024×1024, with bounded decoding memory (16MiB) and a maximum
   saved file size of 8MiB. The image width and height must equal the
   explicit generation request, otherwise the job fails verification.
6. Successful verification returns only the filename, hash, actual
   dimensions, seed, timing, and optional CUDA allocator peak. Raw
   stdout, prompts, and absolute output path are not sent to the webview.
7. The gallery uses the same decoder check before producing a limited
   read-only base64 preview. Malformed files are ignored.

## Why 8 MiB?

Previously the CLI and result verifier accepted PNG files up to 32MiB,
while the desktop gallery only displayed PNGs up to 8MiB. M3-9 aligns
all three paths to the stricter 8MiB limit, so a verified output does
not silently exceed the gallery's supported file-size ceiling.

A valid 8MiB file still may not appear if it is not among the four most
recent files displayed. An oversized PNG is rejected, not recompressed.

## Automated QA

- Rust fixtures use genuinely encoded tiny PNGs instead of files with
  only a synthetic PNG signature.
- Rust tests reject a correct SHA-256 that points to un-decodable PNG
  bytes, wrong model seeds, unexpected JSON fields, fake signatures and
  outside-of-root output paths.
- Gallery tests use actual encoded PNGs, check corrupt data rejection
  and preserve file-count and byte-size limits.
- TypeScript tests assert the new verification state includes dimensions.
- GitHub Actions runs Rust Windows, Python Windows/Linux and frontend
  build and tests. Neither a real SDXL checkpoint nor the RTX 2060 SUPER
  GPU is available in this CI.

## What verification cannot prove

A decodable PNG with a matching hash is a structurally readable image
file. It **does not** guarantee visually attractive output, prompt
adherence, absence of inappropriate content, provenance, CUDA GPU
execution on a particular device, adequate VRAM, or image-generation
speed. Real Windows desktop tests and GPU memory observations remain
required before moving beyond Draft status.

References:
- [PNG Specification Third Edition](https://www.w3.org/TR/png-3/)
- [Rust png decoder reference](https://docs.rs/png/latest/png/struct.Decoder.html)
- [M3-8 telemetry](M3_VERIFIED_GENERATION_METRICS.md)
