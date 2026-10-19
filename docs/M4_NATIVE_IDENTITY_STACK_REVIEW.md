# M4-1j — Win32 synthetic file identity QA + stacked-PR release gate

## Baseline (verified 2026-10-19)

- [M4-1i Draft PR #58](https://github.com/nalkarowndal/tyrfghx/pull/58), head
  `475245ae164d94a15bbf35a079c887d05e85b435`, succeeded in all
  4 general CI jobs on
  [#39246342212](https://github.com/nalkarowndal/tyrfghx/actions/runs/39246342212).
- Prior Draft PRs **#49–#58 are all OPEN, DRAFT and NOT MERGED**.
  GitHub reported them mergeable at review, but `mergeable=true` is
  NOT approval, green integration into `main`, release readiness, or
  evidence of end-to-end Windows deployment.
- M3 and earlier dependencies also remain in a long stacked PR chain;
  do not skip earlier bases.

## Implemented (M4-1j, Windows Rust tests only)

`src-tauri/src/native_fixture_handle_qa.rs` already builds solely
under `#[cfg(all(test, windows))]`. This increment adds
`GetFileInformationByHandle` on owned native handles and compares
`(dwVolumeSerialNumber, nFileIndexHigh, nFileIndexLow)` as an **object
identity**. The test rejects zero reported hardlink counts; for the
two allowlisted tiny synthetic child basenames, it additionally
rejects more than one hardlink. Ancestor handles are retained and
duplicate object identities in a single fixture ancestor walk fail
closed. The existing `FILE_FLAG_OPEN_REPARSE_POINT` and
`FILE_ATTRIBUTE_TAG_INFO` checks remain.

New Windows-native tests prove:
- Two independently opened handles of one mock file report identical IDs.
- Two different temporary mock files report different IDs.
- A temporary hardlink alias (if supported by Windows CI) is rejected,
  and original bytes remain untouched.
- A matching object identity does not bypass the synthetic
  basename allowlist.

The module is never exported through the Tauri command list or the
FastAPI backend. The code never hashes, reads, imports, downloads,
installs, extracts, launches or executes any actual AI package,
model, Python runtime, GPU or CUDA worker.

## Hard limitations — not production-safe

This is **not atomic handle-relative object traversal**. Calls still
open each full pathname separately; malicious concurrent renames,
replace or reparse swaps can occur between opens. Retaining kernel
handles and comparing object identities is useful *negative-regression
QA only*. File IDs and link counts have volume/filesystem-specific
behavior, especially on non-NTFS volumes or network shares; the
test fixture scope is limited to standard Windows CI local temporary
storage. This code is not an authorization gate for arbitrary local
wheels, installers, GPU operations or packages from PyPI.

No claim of trusted publisher signatures or fully hash-pinned
transitive dependencies is made. These must be independently designed
and validated *before* any future package installation.

## Dependency-order review gate (do not merge automatically)

| Stage | Draft PR | Depends on | Current security role |
| --- | --- | --- | --- |
| M3-Final | [#49](https://github.com/nalkarowndal/tyrfghx/pull/49) | M3-46 chain | Frozen release boundary |
| M4-1 | [#50](https://github.com/nalkarowndal/tyrfghx/pull/50) | #49 | CPU-only worker protocol |
| M4-1b | [#51](https://github.com/nalkarowndal/tyrfghx/pull/51) | #50 | Auth proof preview |
| M4-1c | [#52](https://github.com/nalkarowndal/tyrfghx/pull/52) | #51 | Win32 test-only stdio worker |
| M4-1d | [#53](https://github.com/nalkarowndal/tyrfghx/pull/53) | #52 | Offline wheel manifest preview |
| M4-1e | [#54](https://github.com/nalkarowndal/tyrfghx/pull/54) | #53 | Synthetic file SHA preview |
| M4-1f | [#55](https://github.com/nalkarowndal/tyrfghx/pull/55) | #54 | Synthetic Wheel RECORD parsing |
| M4-1g | [#56](https://github.com/nalkarowndal/tyrfghx/pull/56) | #55 | Synthetic classic ZIP framing |
| M4-1h | [#57](https://github.com/nalkarowndal/tyrfghx/pull/57) | #56 | Native fixture handle checks |
| M4-1i | [#58](https://github.com/nalkarowndal/tyrfghx/pull/58) | #57 | Ancestor component regression |
| M4-1j | New stacked Draft | #58 | Native fixture identity/links |

### Required manual integration process

1. Stop creating new operational features until a reviewer audits the
   base M3 PRs and the full dependency chain back to `main`.
2. Confirm no unexpected Tauri/frontend invoke permissions, shell
   launch routes or releases enabling inference; review destructive
   model/import and local installer boundaries separately.
3. Check changes and final merged-tree builds on `main` in dependency
   order. A **stacked PR's own green CI is not evidence that its code
   is already in `main`**. Rebase/retarget and rerun verification after
   each approved merge, never merge the whole chain blindly.
4. Preserve user data, previously installed Windows backend, NSIS
   rollback and fail-closed GPU policies in actual clean Windows
   installation and update smoke tests.
5. Before any production package access, secure handle-relative native
   source inspection, signed/provenance-verified allowlist and complete
   dependency lockfile. Explicit owner consent is required for
   download/install and a separate opt-in for GPU probes and inference.

## Acceptance

- [ ] Latest exact-head Windows Rust native tests including M4-1j pass.
- [ ] Latest exact-head frontend, Linux Python, Windows Python pass.
- [ ] All existing production permissions, API routes, backend worker
  launch and release artifacts remain unchanged.
- [ ] Draft only; no merge and no release.

Sources:
- [Microsoft GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle)
- [windows-sys 0.61.2 definition](https://docs.rs/windows-sys/0.61.2/windows_sys/Win32/Storage/FileSystem/struct.BY_HANDLE_FILE_INFORMATION.html)
- [Tauri 2 capability security](https://v2.tauri.app/security/capabilities/)
