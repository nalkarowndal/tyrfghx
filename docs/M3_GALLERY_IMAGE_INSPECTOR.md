# M3-21 — Interactive local PNG gallery inspector

M3-21 makes the existing React/Tauri image generation workspace
more useful **without requiring inference or a local GPU**. It builds
on the bounded, native, read-only PNG gallery introduced in M3-2.

## User-facing features

- Click **확대해서 보기** under an existing gallery PNG to open
  an inline image-inspection region.
- Switch between the gallery's already available images with
  **이전**, **다음**, or Left/Right arrows while focused in the
  inspection region. Escape closes the inspector.
- Inspect the image at a bounded **50%, 100% or 200% CSS pixel width**
  relative to native decoded PNG dimensions. The panel scrolls instead
  of expanding the whole app window on oversized images.
- Read native-decoded PNG dimensions and file size without opening
  model weights, interrogating the GPU or displaying private prompts.
- A refreshed gallery invalidates any selected image that no longer
  appears in the current verified preview list. Navigating does not
  construct image paths or download external images.
- All primary actions are normal keyboard-focusable buttons with
  explicit Korean names; no hidden autoplay or background work.

## Tauri security boundary

The only Rust addition is two numeric dimensions, `width` and
`height`, on existing `GenerationPreview` objects. Values come
from the existing `generation_result::decode_png` call, which
performs bounded native PNG CRC/chunk verification and decoding.
The fixed `outputs` directory, strict `aiimage-<32 hex>.png`
allowlist, file-size limit of 8MiB, 500-entry scan limit and maximum
of four previews are unchanged. The browser does not receive a native
file path or any filesystem capability.

The frontend's selected item must be present in the currently
received verified gallery; arbitrary IDs and missing items resolve
to no selected image. Zoom is deliberately clamped to 50, 100 and
200 percent. Keyboard handlers are attached only to the inspector
region and do not listen globally, so a form's arrow keys remain
unaffected.

## Limitations and QA

- This is a UI for inspecting already-generated PNGs, not a visual
  quality classifier, reference-image comparison tool, Krea-style
  editing engine, or automatic prompt-adherence measurement.
- Displaying a PNG is not proof that it was rendered by a particular
  GPU, model or generator. M3-20 separately offers owner-run
  checksum/structure verification against a generation report.
- The saved output file contents and native-rendered UI still need
  manual inspection on the owner's Windows machine. GitHub CI tests
  pure selection/navigation/zoom/dimension functions and native PNG
  preview metadata using synthetic files, with **no NVIDIA GPU**.

References:
- React controlled state and Effect cleanup: https://react.dev/reference/react/useEffect
- WAI-ARIA keyboard interaction guidance: https://www.w3.org/WAI/ARIA/apg/
- M3_INDEPENDENT_PNG_QA.md
