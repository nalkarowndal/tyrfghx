# M3-39 — Windows local API bundle

## Design

Base: M3-38 `60266583123d5a3fd699cad932b95185dd8d9c6b`, stacked on PR #40.
The existing FastAPI application is a read-only catalog/status API. GPU generation
is a separate, consent-gated Rust/Python CLI and remains unchanged and disabled
in release builds. Packaging this API does not package CUDA, Diffusers, SDXL or
models, nor make release image/video generation available.

Choose PyInstaller **onedir**, built on Windows x64 with Python 3.12. Unlike
onefile, this avoids per-launch temporary extraction and a second bootloader
process on Windows. A separately installed Python would defeat self-contained
installation. Keep the existing frontend-shell QA overlay; add a separate backend
overlay and `bundled-backend` Cargo feature, so ordinary/E2E builds retain their
current behavior. The onedir folder is a Tauri resource, not a lone externalBin:
all interpreter DLLs must keep their relative paths.

Rust starts only the fixed bundled executable on the initial desktop status
request. It serializes start/status/restart, keeps the child and Job Object,
and assigns the suspended process before resuming it. Python binds exclusively
to `127.0.0.1:0`, generates a fresh 256-bit bearer token, and reports readiness
over its private stdout only after startup. Rust consumes this bounded handshake
and proxies the fixed status endpoint; the webview never receives a port/token
or arbitrary HTTP/process interface. The packaged API rejects missing/wrong
tokens, non-loopback peers, unexpected Host and all Origin headers (including
preflight). API docs are disabled. The existing explicit browser dev server
retains its read-only routes and restricted CORS.

The child's stdin is its lifetime lease: EOF requests graceful shutdown. Rust
waits a bounded time, then terminates/verifies the whole Windows job. App crash
closes the kill-on-close Job Object. Crashes/startup timeouts latch an error;
explicit retry starts a fresh process/token only after cleanup is verified.
A Windows named mutex keyed by canonical model root prevents two app instances
from owning API processes for the same data. Do not attach to a preexisting port
or kill an unowned PID. A second app reports a recoverable startup failure.

Pass the existing native model root over stdin; never derive user storage from
the installation folder. No migration, model download, inference, uninstall
cleanup of application data, or writes to model files. Installer payload stays
under the install directory; existing user data remains outside it.

## QA and limitations

Use synthetic data under temporary directories only. Cover authentication,
Origin/Host/peer restrictions, occupied ports, stdin EOF, invalid startup,
duplicate ownership, crash/restart, token rotation and data preservation.
Test the frozen executable and real Rust manager on Windows, build the NSIS
payload, validate PE/SHA-256, and check Cargo.lock/production WebDriver isolation.
No public artifacts, releases, signing or main merge. Installer execution and
clean-machine/SmartScreen/UAC/real GPU validation must be reported separately
from build/process QA. The default shell installer remains available unchanged.

Official references checked through Context7 and Exa:
- https://v2.tauri.app/develop/sidecar/
- https://v2.tauri.app/develop/resources/
- https://pyinstaller.org/en/stable/operating-mode.html

## Baseline evidence verified 2026-10-19 (KST)

- M3-38 CI [39142271443](https://github.com/nalkarowndal/tyrfghx/actions/runs/39142271443): all four jobs succeeded.
- M3-38 NSIS [39142283706](https://github.com/nalkarowndal/tyrfghx/actions/runs/39142283706): build, PE/hash verification, unchanged Cargo.lock and production dependency check succeeded. Old unchecked documentation is stale.

M3-39 results are recorded after execution; this design is not a completion claim.
