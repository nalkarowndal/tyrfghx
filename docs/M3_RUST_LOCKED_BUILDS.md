# M3-36 — Rust dependency resolution and locked CI

## Why the change

The aiimage desktop binary has an npm lockfile but did **not** track
`src-tauri/Cargo.lock` through M3-35. A successful Rust compile without
that file may select different compatible dependency versions on a later day.

Cargo's authoritative documentation states that `cargo generate-lockfile`
resolves packages and creates the lock, and that `--locked` fails if that
file is absent or a dependency manifest would change the resolution.

- https://doc.rust-lang.org/cargo/commands/cargo-generate-lockfile.html
- https://doc.rust-lang.org/cargo/reference/resolver.html
- https://doc.rust-lang.org/cargo/faq.html

## Controlled generation — do not fabricate Cargo.lock

The explicit label-only workflow
`.github/workflows/generate-rust-lockfile.yml` takes the **same-repository**
source branch and asks the hosted Rust Cargo toolchain to create the real
dependency lock:

```bash
cargo generate-lockfile --manifest-path src-tauri/Cargo.toml
cargo metadata --manifest-path src-tauri/Cargo.toml --format-version 1 --locked
cargo metadata --manifest-path src-tauri/Cargo.toml --format-version 1 --locked --features e2e-webdriver
```

The second feature set verifies that the optional embedded WebDriver
dependency is part of the locked graph, but **does not activate a WebDriver
server**. The workflow checks both the `aiimage` and embedded plugin
package entries and commits **only the lockfile** back to that source PR
branch. The push is non-force; a simultaneous branch update must fail rather
than overwrite another author.

The workflow has write permission and must not run on untrusted forks or
without a maintainer's explicit `generate-rust-lockfile` label. It never
executes application code, launches a GUI, starts GPU inference or reads
private model weights.

If the repository forbids GitHub Actions writes to a source branch, the
workflow retains the generated lockfile as a short-lived review artifact.
Do **not** claim a lockfile was committed until GitHub actually confirms it.

## After the lockfile is committed

Regular Windows Rust CI should use:

```powershell
cargo test --manifest-path src-tauri/Cargo.toml --lib --locked
```

Explicitly authorized Windows GUI jobs should first check the lockfile with
`cargo metadata --locked` including the `e2e-webdriver` feature, and
fail if either the normal or feature-gated build changes Cargo.lock.

The normal production binary must still exclude the embedded HTTP WebDriver
feature. The special test-only executable must still require both runtime
opt-in flags; no package containing this test server may ship.

## Actual verification limits

M3-35 [ordinary CI](https://github.com/nalkarowndal/tyrfghx/actions/runs/39137882679)
and [opted-in native Windows test](https://github.com/nalkarowndal/tyrfghx/actions/runs/39137902929)
passed, including four incomplete-runtime-authorization negative cases.
Real model-catalog transient error/retry remains `not_exercised`.

A Cargo lockfile improves **dependency-version repeatability**, not exact
binary reproducibility across toolchain versions, OS, build scripts,
timestamps, GPU driver/SDK, hardware or registries. Test on a real owner
RTX 2060 SUPER 8 GB before making GPU performance claims.
