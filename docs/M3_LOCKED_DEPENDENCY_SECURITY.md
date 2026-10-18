# M3-23 — Locked and audited JavaScript development dependencies

M3-23 fixes the previous dependency drift and three advisories found
during Windows CI's `npm install`. It does **not** add inference,
WebView2 permissions, a model download path, or a release executable.

## What was found

The previous GitHub-hosted Node 22 resolution reported **three npm
audit findings: 1 moderate and 2 critical**. The reported vulnerable
dependencies were the **development-time Vitest 3.x toolchain**, not
a proof of an exploitable bug in the packaged aiimage GUI:

- `vitest` / `@vitest/mocker`: path traversal / arbitrary local read
  in mock redirection (GHSA-82fw-gwwq-j7x9).
- `tinypool`: prototype pollution gadget and possible arbitrary
  execution in worker options (GHSA-5gmw-xhrv-c9v3 and
  GHSA-85c8-ppgw-ccpr).

The npm audit results came from the **GitHub-hosted build**. They are
not a local security scan of the owner's Windows PC.

## Changes

- Upgrades direct `vitest` requirement from `^3.0.0` to
  `^5.0.5`, and `vite` from `^6.0.0` to `^6.4.0`.
- The Node 22 GitHub runner resolved Vitest 5.0.5 and Vite 6.4.4.
  Its first post-upgrade `npm audit --json` returned:
  **0 critical, 0 high, 0 moderate, 0 low** findings, based on npm
  advisory data **at the time of that run**.
- Commits the npm v3 `package-lock.json` produced by the GitHub
  Node 22 runner; roughly 149 root/transitive package entries.
  No registry credentials or private source URLs are embedded.
- Changes Linux frontend and Windows Rust CI jobs from `npm install`
  to clean `npm ci --no-fund`.
- Adds `npm audit --audit-level=moderate` to the frontend CI job:
  builds fail when any current moderate-or-higher advisory is found,
  instead of displaying a warning and silently passing.
- The Windows development checker now checks for
  `package-lock.json` and Node >= 22.12.0, consistent with Vitest 5.
  Documentation and manual installation guidance now use `npm ci`.
- Removes the **temporary lockfile capture workflow** used for
  creating the initial reviewed lock on a network-enabled GitHub
  runner. It does not remain in the final project tree.

## Owner workflow

From the project root, after pulling the M3-23 branch:

~~~powershell
.\scripts\windows-dev.ps1
npm ci
npm run build
npm test
.\scripts\windows-dev.ps1 -Start
~~~

`npm ci` **installs JavaScript packages from the registry**, so an
internet connection is required for a fresh cache. It does not
download SDXL checkpoints, install CUDA or start image generation.
The default script invocation is read-only; only `-Start` invokes the
existing Tauri local debug UI. None of these commands certifies GPU
rendering.

GitHub CI additionally checks Windows Rust and Python unit tests.
The actual owner's NVIDIA RTX 2060 SUPER 8GB, driver, WebView2 and
Tauri GUI acceptance remain unverified by remote CI.

## Limitations and follow-up

A clean advisory report only means npm did not report **known**
vulnerabilities in the currently locked JavaScript dependency tree.
It cannot guarantee a package is safe, and npm advisories can change.
Other ecosystems (Python/PyTorch, Rust crates, native OS dependencies)
need separate review; this milestone does not change their versions.

The dependency tree contains updates across a Vitest **major
version**. Our app's unit-test suite and frontend build must pass in
CI, and no `npm audit fix --force` is run to conceal breakages.

References:

- https://docs.npmjs.com/cli/v11/commands/npm-ci/
- https://docs.npmjs.com/cli/v11/commands/npm-audit/
- https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json
- https://vitest.dev/guide/migration/
- https://github.com/advisories/GHSA-82fw-gwwq-j7x9
- https://github.com/advisories/GHSA-85c8-ppgw-ccpr
- [M3-22 Windows developer startup](M3_WINDOWS_DEV_LAUNCH.md)
