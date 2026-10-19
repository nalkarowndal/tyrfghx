# M4-Integration — source convergence review

**Status:** unmerged Draft candidate; not a public release, no real AI inference verified.

## What was integrated

- Previous M3/M4 full stack tip: [PR #59](https://github.com/nalkarowndal/tyrfghx/pull/59), `7bcd260d1c015f89d699665691784df2f8834330`.
- Updated M2 source: [PR #1](https://github.com/nalkarowndal/tyrfghx/pull/1), `0570f14fc349ddc6ddf4d159549d0ad2ef77b64d`.
- Shared divergence ancestor: `77f37da86f2986189c03d0c613951c8b0611fa1e`; GitHub compared **26 M2-only commits** and **439 stack-only commits**.
- Created a **separate** `integration/m4-converged-m2-m4` candidate starting at PR #59. Original PR branches are unchanged.
- Ported upstream M2 Python importer, integrity writer, 2 helper modules, 2 test modules and 2 review docs (8 paths).
- **Manually reconciled** `src-tauri/src/model_import.rs`: M2 cooperative cross-language manifest lock, fail-closed stale/corrupt handling, Windows final-component reparse source guard, non-destructive manifest-failure policy and native synthetic tests. Preserved all later M3/M4 Rust integration tests.
- **Manually reconciled** `.github/workflows/ci.yml`: preserved the later M3-Final release audit, npm audit, locked Rust build, Windows policy checks and frontend tests. Added backend Python dependencies in the Windows native Rust test job for real cross-language Pydantic writer QA.
- A two-parent candidate history, if present, is solely an isolated Git history convergence. It is **not** a GitHub PR merge, a change to `main`, review approval or permission for package installations.

## Required current-branch evidence

- [ ] PR-triggered exact-SHA 4/4 frontend/Node, Linux Python, Windows Python and Windows Rust CI success.
- [ ] Native Windows Python–Rust shared registry writes, concurrent model imports and synthetic orphan-review tests pass alongside older M3/M4 regression tests.
- [ ] Windows *installed* NSIS/bundled-backend/GUI QA against the convergence SHA, if supported by the current CI workflows; older PR runs are not a substitute.
- [ ] Static inspection of Tauri commands, native path security, release CSP, installer hooks, lockfile integrity and workflow permissions.
- [ ] Owner-review of [Issue #61](https://github.com/nalkarowndal/tyrfghx/issues/61) path races, lock tampering and unregistered model recovery; unproven production paths must remain disabled.
- [ ] Repository owner-approved branch protection, PR review and merger strategy for 58 dependent Draft PRs. Never auto-merge all 58.
- [ ] Only after integration gates, enter [M4-2](https://github.com/nalkarowndal/tyrfghx/issues/63) with separate explicit GPU, download/install and user model consent.

## Scope limits

This integrated code may compile and run tests, but no hosted GitHub Actions test can prove generation on the user's NVIDIA RTX 2060 SUPER 8GB, driver/torch/CUDA compatibility, trusted wheel provenance or a signed consumer release. Any installed-app QA uses hosted Windows synthetic fixtures only.

[Integration work item #60](https://github.com/nalkarowndal/tyrfghx/issues/60) · [Milestone policy #62](https://github.com/nalkarowndal/tyrfghx/issues/62) · [GitHub stacked PR docs](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests)
