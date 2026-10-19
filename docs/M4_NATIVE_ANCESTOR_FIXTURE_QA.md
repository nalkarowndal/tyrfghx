# M4-1i — Synthetic Win32 ancestor-component handle QA

## Parent baseline

The prior [M4-1h Draft PR #57](https://github.com/nalkarowndal/tyrfghx/pull/57),
commit `e5412a6e029c63994430d02e18ef34600683899f`, passed all four general
checks in [CI #39244162967](https://github.com/nalkarowndal/tyrfghx/actions/runs/39244162967).
Windows Rust reported 62 passing tests, 2 ignored. The older M2/M3/M4 Draft
stack remains **unmerged** and requires review before production integration.

## Scope: negative regression QA for disposable directories

The only changed native code is
`src-tauri/src/native_fixture_handle_qa.rs`, already included exclusively
via `#[cfg(all(test, windows))]`. It is not included in any normal release,
and is never a Tauri command, webview API or FastAPI route.

Before opening a **synthetic** fixture named `sample.whl` or
`fixture.marker`:

- Reject non-absolute paths, UNC/SMB paths, Win32 device/verbatim namespaces,
  drive-relative roots, parent traversal and other non-normal components.
  This is a deliberately narrow *local drive* test policy, not a
  general Windows filesystem policy.
- Start at the drive root and open each absolute ancestor (through to the
  temp fixture root) with `CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT |
  FILE_FLAG_BACKUP_SEMANTICS)`, retain each owned handle, and fetch
  `FILE_ATTRIBUTE_TAG_INFO` to reject symlinks, junctions and other
  filesystem reparse points at the checked component.
- Query each handle's final DOS path via `GetFinalPathNameByHandleW`
  without equating adjacent components' displayed path strings: Windows
  short-name, drive-alias or canonicalized path spellings may differ even
  for legitimate fixture directories. Still open the allowed synthetic
  child with `FILE_FLAG_OPEN_REPARSE_POINT` and compare its handle path
  against the fixture root as in M4-1h.
- **CI regression learned:** the first Windows Rust run failed seven
  native fixture assertions because the new adjacent string comparison
  incorrectly returned `fixture_parent_denied`. The false-positive
  comparison was removed, but native no-follow attribute checks remain.
  Retained handles do not guarantee ancestry across concurrent renames.
- Extend Windows-native Rust QA for nested regular directories, a
  symlink **grandparent**, absolute device/UNC/parent-traversal denial,
  and confirmation that fixture bytes are unchanged after inspection.
  Symlink-creation cases run where Windows permits creating test links.

No wheel bytes, AI model, local Python installation, GPU, inference worker,
installed application, actual user-selected path, or remote package source
is inspected by this test code.

## Important limitations

These checks are **not sufficient for safe production arbitrary-path
handling**. Opening full path strings in sequence is not the same as
handle-relative, atomic component traversal; another process may swap,
rename or reparse an ancestor between calls. Even retained handles do
not make later string-based child opens race-free, especially with delete
sharing enabled. This fixture-only policy also cannot establish trusted
software provenance, verify full dependency closure or authorize a pip
installation. The checked drive path must be local, and no claim is made
about UNC/network share support, alternate name aliases, ACL scope or
general Windows path protection.

The next production-design phase needs Windows-native handle-relative
resolution, file object identity invariants, trusted roots and explicit
caller authorization, separately reviewed by a security owner. Any
package install or CUDA/AI inference needs separate, explicit approval.

## Acceptance

- [ ] All 4 exact-head CI jobs pass (frontend, Linux Python, Windows Python,
  Windows Rust locked native tests).
- [ ] No production Tauri command or shell capability added.
- [ ] No model reads, installer changes, downloads, user-data modifications
  or GPU operations.
- [ ] PR remains Draft, stacked on #57 and unmerged.

Sources:
- [Microsoft CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [Microsoft GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)
- [Tauri capabilities](https://v2.tauri.app/security/capabilities/)
