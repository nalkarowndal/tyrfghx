# M3-34 — Production build must NOT expose WebDriver

## Basis: real Windows E2E passed for the first time

[Actual M3-33 embedded Windows E2E run #39135699773](https://github.com/nalkarowndal/tyrfghx/actions/runs/39135699773) finished **successfully** on 2026-10-18.

The hosted GPU-disabled Tauri RELEASE test app built and the Node harness reported:

```text
navigation: passed
missing_checkpoint_preflight: passed
release_gpu_block: passed
consent_unchecked_after_navigation: passed
catalog_error_recovery: not_exercised
native_release_policy: attested_disabled
```

The ordinary M3-33 four-job regression CI also completed successfully:
[run #39135666800](https://github.com/nalkarowndal/tyrfghx/actions/runs/39135666800).

This does **not** test a signed installer, packaged Python sidecar, image
generation on the owner's RTX 2060 SUPER, inference model compatibility or
an actual failed-and-recovered model catalog. Keep these separately tracked.

## Threat model and M3-34 changes

The E2E-only Rust feature compiles an in-app loopback HTTP WebDriver server.
It must never reach a user's normal installation. Code/config feature guards
from M3-33 are necessary, but a negative test of the **actual normal release
binary** gives stronger evidence.

On an explicitly authorized disposable hosted Windows CI runner, the
`Windows embedded UI E2E (opt-in)` workflow now:

1. Builds the **ordinary production-feature RELEASE .exe**, no installer.
2. Runs `windows-production-webdriver-absence.ps1` against **only** that
   checkout's `src-tauri/target/release/aiimage.exe`.
3. Assigns a distinct temporary 127.0.0.1 port and starts the regular
   binary with the same test environment switches that could activate a
   compiled WebDriver feature: `AIIMAGE_E2E_ENABLE=1` and
   `TAURI_WEBDRIVER_PORT=<PORT>`.
4. Requires the release app to remain running and independently probes the
   chosen loopback port repeatedly. **Any listener is a test failure**,
   including a port collision. It does not invoke HTTP endpoints, scan
   unrelated ports, click buttons, access models, perform GPU computation or
   upload logs.
5. Terminates only its spawned process tree, restoring the original
   environment, before starting the E2E-specific feature build.
6. Compiles the **feature-gated test-only** release binary with separate
   permissions and executes the previously passing real embedded GUI checks.
   No E2E-only binary is bundled, signed or uploaded as a release artifact.

The Node launcher is also restricted to the exact canonical release
executable path in the current checkout; it will not run a debug executable,
relative filename or arbitrary alternative `.exe` from a caller-supplied
environment variable.

The normal Windows Rust CI validates the negative-probe path guard using
`-ValidateOnly`, so it does **not** open any GUI or start a listener.
Synthetic Node tests cover the same executable allowlist.

## Limits

This test proves only that the **tested Windows production-feature binary**
does not open an E2E WebDriver listener on the explicitly selected
loopback port while the test variables are supplied. It is not a universal
network audit of all machines and does not prove that every possible custom
packaging/build flag is safe.

The actual negative proof remains **unverified until the opt-in workflow
completes successfully on the M3-34 commit**. Merely adding this script is
not evidence of passing it.

Rust dependency reproducibility remains an open issue: the repository does
not currently include a tracked `src-tauri/Cargo.lock`. An explicit
dependency-lock update and review are required before a production packaging
milestone. Do not claim locked Cargo resolution.

## Commands in opt-in hosted Windows workflow

```powershell
npm ci --no-fund
npm run tauri -- build --no-bundle
./scripts/windows-production-webdriver-absence.ps1 -Application $env:AIIMAGE_E2E_APP
npm run tauri -- build --no-bundle --features e2e-webdriver --config src-tauri/tauri.e2e.conf.json
node scripts/windows-ui-e2e.mjs --run --embedded
```

Official context: https://v2.tauri.app/develop/tests/webdriver/ and
https://webdriver.io/docs/desktop-testing/tauri/plugin-setup/
