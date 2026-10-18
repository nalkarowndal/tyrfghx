# M3-24 — explicit native model SHA-256 recheck

This incremental Tauri model-manager improvement is **read-only**. It compares
one selected local file against the SHA-256 stored during a previous explicit
import. It does not provide trusted model provenance, malware scanning, safe
deserialization, weight loading, GPU qualification or artistic validation.

## Desktop usage

1. Run the Windows Tauri developer UI after preparing its prerequisites.
2. Open **모델 관리**.
3. On a recognized local `.safetensors` checkpoint, LoRA or VAE, click
   **현재 파일 SHA-256 검증**.
4. Interpret the result:
   - **일치**: the bytes observed during this specific check equal the locally
     recorded import hash. This is not a model safety certificate.
   - **불일치**: local file bytes differ from the recorded hash. Do not use it
     until the expected source and checksum have been independently checked.
   - **기록 없음**: no previous import-time hash is stored for this model.
   - **실패**: missing file, inaccessible/corrupt registry, unsafe path, or a
     file changed while being read; the UI deliberately omits native paths.

Large model checks perform disk I/O and can take noticeable time. Only one
verification button is enabled in the UI at a time. This tool does not modify
the model file or the checksum registry, and does not silently rehash on page
load. Gallery/image generation code is unchanged. Refreshing the catalog clears
displayed point-in-time results.

## Data and command boundary

- Only Windows/macOS/Linux Tauri can invoke `verify_local_model_hash`.
  Browser-only builds do not expose this operation.
- Webview sends a **single catalog model ID**, never a filesystem path.
- Rust validates exact category, one filename, `.safetensors` extension and
  rejects traversal, alternate separators and Windows drive/ADS colons.
- Rust uses the existing model root (`model_import::model_root`), reads the
  local `integrity.json` (max 1 MiB), and checks direct regular files only;
  symbolic-link model files/folders are rejected.
- An absent recorded hash returns `not_recorded` **without opening or
  hashing the file**. Malformed registries are errors.
- A registered file is streamed through SHA-256 in bounded 1 MiB blocks,
  with a 64 GiB size cap. Metadata is compared before and after reading.
- Results contain only one of `match`, `mismatch`, or `not_recorded`.
  No model bytes, local paths, prompts or expected/current digests are
  returned to the UI.
- A locally writable hash registry is **not** an independently authenticated
  reference. Maliciously replacing both the model file and its recorded hash
  can produce a match. Hashing only checks the file state observed at that time.

## Verification

CI must pass:
- `npm ci && npm run build && npm test` — browser guard, path validation,
  strict native result handling and existing frontend behavior.
- `cd src-tauri && cargo test --lib` on Windows — registered hash match,
  same-size tamper mismatch, missing or corrupt registry, invalid IDs.
- Existing Linux/Windows Python tests and Windows desktop Rust checks remain.

CI uses tiny synthetic safetensors fixtures. It does **not** perform GUI
interaction, inspect the operator's private models or run RTX 2060 SUPER
inference. The stored-hash verification is a partial improvement to issue #25,
not a substitute for shared root, backend auth and packaged sidecar work.
