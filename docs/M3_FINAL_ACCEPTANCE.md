# aiimage M3-Final — Freeze, verification matrix and release boundary

**State: candidate for M3 feature freeze; not a merged/released milestone.**
Prepared 2026-10-19 (Asia/Seoul). Scope: React/Tauri 2 Windows desktop
shell, authenticated read-only packaged FastAPI backend, native model
catalog/SHA-256, explicit GPU release lockout, Windows installer/upgrade
safety and non-executing optional inference runtime planning.

## Exact baseline and verified evidence

- Source baseline: `feat/m3-46-isolated-ai-runtime-plan` commit
  `2f34d8d32f270f860bc2a92717e5f82830d9696e`,
  [Draft PR #48](https://github.com/nalkarowndal/tyrfghx/pull/48).
- [M3-46 normal CI #39185782079](https://github.com/nalkarowndal/tyrfghx/actions/runs/39185782079):
  **4/4 success** — React/Vitest and Node W3C fake WebDriver;
  Linux and Windows Python; locked Windows Rust.
- [M3-46 actual Windows packaged backend #39185751407](https://github.com/nalkarowndal/tyrfghx/actions/runs/39185751407):
  **completed success** — frozen Python backend auth; actual isolated
  NSIS installation/repair, 0.1.0 -> 0.1.1 version change,
  rejected downgrade, before-write failure exit 83 and safe retry,
  native GUI owned backend crash/restart, and model/output preservation
  on interactive uninstall.
- Native/embedded WebDriver optional workflows on that head were
  **skipped**, not passed. Earlier M3 runs verified real native GUI.
  The actual installed GUI was tested in the packaged-backend workflow.

The new `chore/m3-final-readiness-audit` branch must independently
re-run the normal CI and packaged Windows job before this final
audit can be marked complete. No historical run proves a new commit.

## M3-Final hard stop: code and integration boundaries

`python scripts/m3_final_gate.py` runs a **static, read-only** audit
on the checked-out repository and fails if:
1. Default product config enables bundling or test-only capabilities.
2. Default Cargo features allow test-only embedded WebDriver.
3. Windows bundled API test configuration loses its per-user install
   and original NSIS model/output uninstall-preservation hook.
4. Version/downgrade/preinstall-fault test overlays escape their
   one-purpose isolated config structures.
5. Packaged API auth, non-readiness flags or no-auto-install/no-GPU
   inference plan regress.
6. Frozen read-only backend lockfile acquires Torch/Diffusers/
   Transformers/Accelerate or CUDA runtime requirements.
7. Installed-Windows QA loses any of the previous successful
   version-repair/upgrade/downgrade/failure/retry/GUI/uninstall markers.
8. Hosted Windows workflow stops running those tests, or starts
   uploading installer artifacts or publishing releases.

The `backend/test_m3_final_gate.py` tests intentionally break each of
these boundaries in disposable temporary test directories, verifying
that failures do not silently turn into green checks. Both Linux and
Windows Python CI run the gate. It must not import Torch, touch the
GPU, download models, install software or invoke any external service.

**This automated audit is static; it is not a proof that Windows UI,
NSIS, security, or all 432 earlier commits are correct.**

## Stage exit checklist

| Gate | Necessary evidence | Current interpretation |
| --- | --- | --- |
| Feature freeze | No more M3 features after M3-46 | **Adopted for M3-Final** |
| Latest branch normal CI | 4/4 jobs success for M3-Final SHA | **Pending new CI** |
| Latest branch Windows installed NSIS QA | Successful real hosted Windows job for M3-Final SHA | **Pending new run** |
| Source safety audit | Both Windows/Linux read-only static audit PASS | **Pending new CI** |
| Review open stacked PRs | Chain, base branch and review status verified; security regressions resolved | **Pending human review** |
| Release risk register | Known limitations recorded below and M4 handoff approved | **Documented, awaiting review** |
| main integration | Explicit approval and authorized ordered merge | **Not authorized or performed** |
| Production distribution | Signed release, verified clean PC/device, release GPU policy reviewed | **Out of scope, not passed** |

A maintainer may call M3 *feature complete* after the first four
gates, but **cannot call it fully integrated or publicly released**
until the separate review/merge/release gates are met.

## PR stack and merge plan

At snapshot the repository was **432 commits ahead of `main`**,
with **46 M3 Draft PRs open**. It has a long dependent chain starting
at M3-1 [PR #2](https://github.com/nalkarowndal/tyrfghx/pull/2)
above `feat/m2-local-model-catalog`, and continuing through
[PR #48](https://github.com/nalkarowndal/tyrfghx/pull/48)
and this M3-Final candidate. Thus the whole chain cannot simply be
declared merged or isolated from the underlying M2 trunk. Existing
PR base references and new GitHub stacked PR semantics must be
inspected before any integration.

**No automatic merge, auto-merge, retarget, squash, force-push,
main write or readiness-for-review change** is allowed here.
Recommended subsequent authorized procedure: review each dependent
PR in base-to-head order, resolve branch/merge conflicts and required
checks, ensure M2 prerequisite trunk is approved, merge by approved
method, and re-run the entire regression matrix on the resulting
integration branch. Latest-head checks alone do not validate
`main`.

Official GitHub stack guidance:
https://docs.github.com/en/pull-requests/reference/stacked-pull-requests

## Important known risks retained, not swept into M4 as 'done'

- Product `src-tauri/tauri.conf.json` still has `app.security.csp=null`.
  A secure, narrowly scoped CSP is a **production-distribution blocker**
  until its Tauri/WebView and plugin implications are reviewed.
- No user-PC clean-install / restart / Windows SmartScreen / signing /
  MSI/NSIS public-release verification; the QA installer remains
  **unsigned, nonpublished, backend read-only and GPU-disabled**.
- Real Windows native UI occasional startup flake was previously
  recorded. Later successful runs do not prove the underlying cause
  has been eliminated.
- Packaged API's Torch/version checks inspect only its own interpreter;
  they do **not** detect a selected inference venv or prove CUDA
  availability. No GPU probing or image/model execution has passed.
- User data migration between **different model database schemas** and
  true **mid-write transaction rollback** are untested. M3's early
  pre-install abort is not a transaction rollback.
- `main` is not integrated. Large stacked changes require a separate
  owner-approved review plan and release security audit.

## M4 ownership boundary

See [M4 handoff](M4_INFERENCE_ENGINE_HANDOFF.md).
The next stage must work on a **new isolated inference-runtime branch**
created only after the above evidence is reviewed. It may design
dependency installation, hash checks and user consent; actual CUDA
probes, model loads and GPU inference require explicit user approval.
Production build remains GPU-disabled until its own release-specific
security signoff.
