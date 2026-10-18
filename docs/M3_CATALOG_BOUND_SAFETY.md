# M3-28 — Catalog-bound checksum verdicts and explicit GPU consent

## Problem and resolution

M3-27 correctly clears old model lists when a refresh starts. But a native
SHA-256 verification or async checkpoint/LoRA comparison launched **before**
that refresh may finish **after** the new catalog is displayed. Without request
identity checks, the old result could appear under a new file with the same
catalog model ID.

M3-28 adds an independent catalog epoch and an active request ID to the
model-manager UI:

- A model list replacement, loading/error change, manual refresh or successful
  import invalidates all earlier hash and compatibility results.
- New selections invalidate a pending checkpoint/LoRA compatibility comparison.
- A late successful/failed Tauri SHA-256 request cannot restore a stale match
  or error for a new catalog or an unrelated click.
- Busy state and obsolete selection are cleared on refresh. A native disk read
  that already started is **not terminated** by this frontend guard; it is
  deliberately ignored upon completion.
- A displayed 'match' is **only a point-in-time check against the local
  import registry**. It is not signed provenance, GPU validation, malware
  scanning or protection against a model changing after the check.

For image generation, explicit GPU consent now refers to the **exact loaded
model catalog array identity** at the moment the user ticks the checkbox:

- Refresh, catalog replacement, loading or failure immediately makes the
  prior consent ineligible in the **launch predicate**, even before React's
  cleanup effect clears the visible consent/VRAM-risk checkboxes.
- A new catalog with the same model ID still requires new GPU consent.
- Changing prompt/settings or selecting a new checkpoint still clears consent.
- Refresh does not auto-retry GPU work or cancel an already running native job.
- The native Rust GPU safety checks, consent requirement and 8 GiB VRAM
  guidance are unchanged. The user must separately run a real Windows/RTX
  acceptance test when appropriate.

## CI checks

- `npm run build` and `npm test` include pure Vitest tests for identity-bound
  consent, stale same-ID catalogs, loading and failure, plus two-dimensional
  native request guards for delayed success/error.
- Existing native model/import integration, Python/Linux/Windows regressions,
  WebDriver protocol mock suite and Windows Rust tests remain unchanged.
- Real Windows Tauri UI E2E remains an **opt-in, separate workflow** and is
  not implied by regular CI success.

## Manual Windows verification (no GPU operation)

With a safe synthetic catalog or synthetic model QA fixture on an owned Windows
developer machine:

1. Open **모델 관리**, choose a test item and click
   **현재 파일 SHA-256 검증**.
2. While a test-only long hash operation is pending, replace/refresh the
   catalog. The old response must not appear under a newly loaded model.
   Do not modify private real weights; use disposable fixtures only.
3. Switch checkpoint/LoRA selectors while compatibility checking. Old
   comparison results must not appear under the new selection.
4. In **이미지 생성**, select a metadata-valid test checkpoint, enter a
   prompt and check the GPU consent box **without clicking GPU 생성 시작**.
   Refresh/replace the model list. Verify consent is cleared and launching
   remains disabled, even if the same model ID reappears.
5. Verify VRAM-risk override is also cleared after refresh. An already-running
   native job, if any, requires independent job management; this UI reset does
   not claim successful native process cleanup.

Record separate pass/fail/not_tested evidence for UI click behavior, real RTX
2060 SUPER 8 GB inference and GPU cleanup. No actual GPU jobs were launched
by the M3-28 code changes or unit tests.

References:
- https://react.dev/reference/react/useEffect#fetching-data-with-effects
- https://react.dev/learn/preserving-and-resetting-state
