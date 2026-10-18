# M3-32 — Isolating native Windows launch from WebDriver session startup

## Observed evidence, 2026-10-18

The two explicitly enabled hosted Windows GUI tests against the stacked
aiimage development branches failed at different stages:

- [M3-30 first attempt](https://github.com/nalkarowndal/tyrfghx/actions/runs/39132228233):
  Tauri release compilation, tauri-driver and EdgeDriver setup passed;
  the direct WebDriver smoke stopped at an unclassified 12-second timeout.
- [M3-31 reattempt](https://github.com/nalkarowndal/tyrfghx/actions/runs/39132902971):
  the same prerequisites passed, but the WebDriver **POST /session** request
  returned the standardized **session not created** error after about 61 seconds.
- All four ordinary M3-31 CI jobs (frontend/Node, Linux Python, Windows Python,
  Windows Rust) passed. None of those prove desktop GUI accessibility.

The first observation was ambiguous; the second isolates a **native WebDriver
session creation problem**. It does not prove whether Windows hosted CI has
an interactive window station, whether the app exits on startup, or whether
the EdgeDriver fails to attach to its WebView2. Do not claim any of those as
the definitive root cause without additional observations.

## M3-32 diagnostic probe

A new script, `scripts/windows-release-window-probe.ps1`, runs only within
the explicitly opted-in, **GPU-disabled** Windows release E2E workflow.

Before the WebDriver session attempt, the probe:
1. Validates the executable path is **exactly**
   `src-tauri/target/release/aiimage.exe` in the checked-out repository.
2. Starts that binary **without a WebDriver, model import or GPU action**.
3. Waits up to approximately nine seconds for the process to exit or report
   a main window handle.
4. Emits **only a safe outcome category**:
   - `main_window_handle_observed` — a Windows window handle was reported.
   - `process_alive_window_not_observed` — process stayed alive but the
     current CI session did not expose a main window handle. This is *not*
     proof that no window exists.
   - `process_exited_before_window` — process exited before a window was seen;
     this is a launch failure and the workflow fails closed.
5. Terminates only its launched process tree before starting the WebDriver
   service; it does not collect screenshots, paths, prompts, full logs or files.

The standard Windows Rust CI invokes the probe **only with -ValidateOnly**,
which validates its path restriction without opening an application window.

The direct WebDriver harness now reports the exact safe error category
`native_session_not_created` if the W3C server rejects native session
creation. Other server-provided error text is allowlisted instead of echoed
verbatim to avoid disclosure of private model locations.

## Follow-on architecture

The official Tauri documentation (updated 2026-06-29) recommends
`@wdio/tauri-service` and the embedded WebDriver provider. The embedded
provider requires deliberate Rust and npm plugin integration and should
remain **test-only**, never unintentionally enabled in a production binary.
It avoids reliance on the external `tauri-driver`/EdgeDriver attachment
mechanism but is not implemented or validated in this PR.

- Official: https://v2.tauri.app/develop/tests/webdriver/
- Manual external driver: https://v2.tauri.app/develop/tests/webdriver/manual-setup/
- WebDriverIO: https://webdriver.io/docs/desktop-testing/tauri/

## Acceptance criteria and limits

- Existing React/TypeScript, mock W3C WebDriver, Windows/Linux Python, and
  Windows Rust CI must pass.
- Only a **successful opt-in native WebDriver run** can establish actual
  hosted Windows desktop click-through. A probe success alone is not enough.
- The owner's local Windows desktop, RTX 2060 SUPER 8 GB, real SDXL inference,
  model weight loading, Python sidecar and packaged installer remain untested.
- No automatic main merge or actual GPU computation is part of M3-32.
