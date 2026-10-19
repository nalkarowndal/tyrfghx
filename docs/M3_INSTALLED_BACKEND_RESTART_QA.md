# M3-40 — Installed Windows GUI backend restart acceptance

## Purpose

M3-39 verified the installed NSIS application, bundled Python API authentication,
normal-close and parent-crash cleanup, and uninstall data preservation on a
disposable GitHub Windows runner. The Rust process manager and frontend restart
loader also passed unit tests, but **the installed app's restart button was not
clicked by UI automation**. This milestone adds that missing end-to-end check.

The only GitHub test host is the Windows hosted runner. No owner's computer,
real models, prompts, GPU device or inference libraries are involved.

## Actual installed UI exercise

The existing `scripts/windows-installed-backend-qa.ps1` now runs three
isolated app scenarios on the disposable runner:

1. `normal_close`: start installed UI, confirm its genuine read-only Python API,
   reject unauthenticated loopback HTTP requests, close the app, verify its
   backend child has exited.
2. `parent_crash`: start again, kill **only the owned Tauri parent**,
   verify the Windows Job Object removes the owned backend child.
3. `restart_after_backend_crash`: start a third independent installed app,
   observe the connected UI and exactly one owned backend child, then
   terminate **only that child PID**. Wait for the normal app polling loop
   (15 seconds), require an *enabled, visible and UIAutomation-invokable*
   **백엔드 다시 시작** control, call its Windows UIAutomation InvokePattern
   (not direct Rust IPC), and require:
   - the original child PID is gone;
   - exactly one **new**, distinct `aiimage-backend.exe` child appears;
   - the installed app UI once again shows `Python API 연결됨`;
   - the new backend only listens on `127.0.0.1`;
   - unauthenticated access to its fixed `/api/status` endpoint returns 401;
   - normal app close also removes the replacement backend without orphans.

Only after all three succeed does the existing *interactive* NSIS uninstall
QA select the stock delete-app-data checkbox, confirm the custom preservation
hook is effective, and verify synthetic model and output sentinels survive.

## Safety and controls

- The test still rejects any pre-existing app data directory on its
  disposable runner; all model/output fixtures are synthetic.
- No GPU jobs, inference, model downloads, private files, screenshot
  uploads, HTTP tokens in logs, installer publishing or software signing.
- Neither an unowned PID nor a pre-existing local service is killed.
  Cleanup is limited to processes started and observed by this test.
- The existing `bundled-backend` feature and explicit `default`
  production capabilities are unchanged; the embedded WebDriver server
  remains excluded from installed production binaries.
- The test uses UIAutomation in the installed UI without building any
  new WebDriver-enabled production installer.
- Test failures produce short machine-readable
  `installed_qa: <category>` messages, not raw process credentials.

## CI

The workflow `.github/workflows/windows-backend-bundle-qa.yml` now runs for
both M3-39 and M3-40 branches on `push`, building the pinned PyInstaller
payload and temporary NSIS app before testing the installed UI and safe
uninstaller. Regular frontend/Python/Rust PR CI is unchanged.

**Acceptance requires a completed M3-40 Windows packaged-backend QA run
with `installed_qa: installed_gui_restart_click_reconnected_and_no_orphans`
in its logs**, in addition to all other pre-existing tests. Merely adding
the script or passing frontend/Rust unit tests cannot establish a real
installed restart click.

## Known limits

- This is a hosted Windows runner, not a clean end-user Windows VM.
- The intermittent embedded WebDriver test-app startup exit previously
  observed in M3-39 remains separately unexplained.
- The package includes the **read-only FastAPI API**, not
  CUDA/PyTorch/Diffusers, models or release GPU inference.
- The installer is unsigned and not published, and user machine upgrade,
  SmartScreen, offline WebView2 and RTX 2060 SUPER behavior remain untested.

Baseline evidence:
- M3-39 [general CI](https://github.com/nalkarowndal/tyrfghx/actions/runs/39166985947)
- M3-39 [packaged backend QA](https://github.com/nalkarowndal/tyrfghx/actions/runs/39166982954)
- Tauri [WebDriver documentation](https://v2.tauri.app/develop/tests/webdriver/)
