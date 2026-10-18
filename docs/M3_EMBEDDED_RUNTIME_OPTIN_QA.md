# M3-35 — Negative runtime opt-in QA for embedded Windows WebDriver

## Confirmed baseline

The full M3-34 opt-in Windows verification on 2026-10-18 completed successfully:
[GitHub Actions run #39136858492](https://github.com/nalkarowndal/tyrfghx/actions/runs/39136858492).

The hosted Windows runner logged:
- `production_webdriver_absence: verified_no_listener` after building and running the **ordinary production-feature** executable.
- Real embedded GUI E2E PASS for navigation, missing-checkpoint preflight,
  GPU launch disabled, unchecked GPU/VRAM consent and native release policy disabled.
- `catalog_error_recovery: not_exercised`, because no actual transient catalog
  error occurred. Do **not** call this scenario validated by real GUI.

[M3-34 ordinary CI #39136837317](https://github.com/nalkarowndal/tyrfghx/actions/runs/39136837317) passed frontend, Linux/Windows Python and Windows Rust regression jobs.

## M3-35 defense in depth

M3-33 required both a Cargo feature and explicit runtime settings. M3-34
proved that the **ordinary production binary** does not expose the embedded
HTTP test server. M3-35 now proves that even the special E2E-only executable
does not expose a server if the runtime approval is incomplete.

A single, pure Rust function (`embedded_webdriver_authorized`) is used by
actual plugin registration and covered by Rust unit tests. It only authorizes
the HTTP server when:
- `AIIMAGE_E2E_ENABLE` is exactly the string `1`, AND
- `TAURI_WEBDRIVER_PORT` parses as an unsigned 16-bit integer >= 1024.

The Rust tests reject missing, wrong, malformed, privileged and overflow
values, and allow exact approval plus a valid port.

### Explicitly opted-in hosted Windows test

After building the feature-enabled release executable, the workflow runs
`scripts/windows-embedded-runtime-gate.ps1` with that **exact executable**
in an isolated hosted Windows environment. It never runs on the owner's
computer automatically.

It launches and terminates four separate owned app processes without
inference, file-pickers or model modification:
1. Neither flag supplied: default plugin port 4445 must remain closed.
2. `AIIMAGE_E2E_ENABLE=1`, port unset: 4445 must remain closed.
3. Enable set to 1, port malformed: 4445 must remain closed.
4. Valid isolated port set, enable missing: the isolated port must remain
   closed.

Any unexpected listener, process exit, occupied default port, or incomplete
probe **fails closed**. Each case requires the app to remain running over
multiple probes. A false positive due to another local process claiming the
tested port is possible but cannot become a false security PASS.

Only after these negative tests does the existing positive real embedded
WebDriver GUI suite launch the same test-only executable with **both**
required settings. No fallback to external driver or unapproved executable
path is permitted.

The normal Windows Rust CI runs the script with `-ValidateOnly` to verify
its binary path restriction without opening any app or HTTP socket.

## Remaining restrictions

- The E2E-feature executable is **never** a distributable, signed package
  or installer and must not be uploaded to end users.
- This proves test scenarios on a hosted Windows runner, not universal
  security of every possible build configuration or the user's machine.
- The repository does not yet commit `src-tauri/Cargo.lock`. Rust dependency
  resolution reproducibility remains a separate prerequisite for a release.
  Do not label the Cargo dependency graph locked or deterministic.
- Synthetic model-catalog fail/retry **passes only mocked W3C tests**; the
  actual GUI has not yet exercised this scenario.
- No real GPU/RTX 2060 SUPER inference, model loading or image validation
  is performed in this milestone.

Official references:
- https://v2.tauri.app/develop/tests/webdriver/
- https://webdriver.io/docs/desktop-testing/tauri/plugin-setup/
- https://doc.rust-lang.org/cargo/faq.html
