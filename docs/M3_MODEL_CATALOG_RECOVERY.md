# M3-27 — Model catalog fail-closed recovery and explicit retry

## What changed

React can race multiple asynchronous model-catalog requests when switching
between **이미지 생성** and **모델 관리** or repeatedly refreshing. A previous
catalog must never silently survive a failed refresh and remain selectable for
image generation. Tauri IPC requests are not abortable in the same manner as
browser fetch, so application cleanup ignores superseded responses.

M3-27 introduces `loadModelCatalog` as a tiny, testable transition boundary:

- As soon as a catalog request starts, clear previously displayed models,
  pending success context, and catalog error; show the loading state.
- Accept data only if the originating section/request is still current.
- Reject malformed payloads, unsupported record kinds, and lists over 3,000
  entries. Never render a half-trusted catalog.
- On a failed request, clear any prior entries and show one static Korean
  message with an explicit **목록 새로고침** recovery action.
- Hide model cards and verification actions while loading or after failure,
  even if a parent mistakenly passes old items.
- Never display raw native path/permission errors from model import or
  metadata comparison; use fixed category guidance.
- Retry browser model requests even when the separate `/api/status` request
  failed earlier, so a restarted Python backend doesn't require reopening
  the application.
- A successful catalog fetch only proves metadata retrieval, **not**
  model safety, checksum authenticity or SDXL/CUDA operability.
- No automatic retry, model download, GPU operation, new dependency, or
  installer generation.

## Existing automated validation

`npm run build && npm test` covers both a pure promise-based recovery
suite and server-rendered UI smoke tests. The promise test simulates:

1. Old checkpoint discarded immediately on refresh.
2. Failed native command carrying a private path replaced with safe text.
3. Delayed superseded success ignored (including unabortable Tauri IPC).
4. Delayed superseded failure ignored without overwriting the new view.
5. Missing/malformed/oversized payloads rejected.
6. User-invoked retry restoring a valid catalog after backend recovery.
7. Already-cancelled load not starting.
8. No stale model SHA-256 verification button/card during loading or errors.

The existing Windows Rust, Windows/Linux Python, WebDriver mock-protocol,
and optional actual Windows UI workflow are left in place.

## Actual Windows acceptance, still pending

On the owner's Windows computer, run the existing development UI intentionally:

```powershell
npm ci
.\scripts\windows-dev.ps1 -Start
```

With a disposable model catalog and no GPU operation:

1. Open **모델 관리**, inspect the current catalog.
2. Temporarily make the **test** model directory inaccessible or otherwise
   simulate a controlled catalog read failure. **Never alter real weights.**
3. Press **목록 새로고침**. Confirm old model cards/actions disappear and
   no native filesystem path is rendered.
4. Restore the test directory; press **목록 새로고침** again.
   Confirm the catalog reappears without app restart.
5. Switch quickly between model management and image generation while
   refreshing. Confirm no old, late response repopulates the wrong view.
6. Confirm generation remains disabled with no usable SDXL checkpoint or
   missing consent.

Record each as passed/failed/not_tested. CI success is not proof of native
GUI execution, owner RTX 2060 SUPER inference, or actual model compatibility.

Reference: https://react.dev/reference/react/useEffect#fetching-data-with-effects
Tauri IPC: https://v2.tauri.app/develop/calling-rust/
