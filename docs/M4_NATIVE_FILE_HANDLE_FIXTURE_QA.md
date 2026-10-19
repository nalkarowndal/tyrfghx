# M4-1h — Win32 native handle checks for synthetic fixtures only

## Verified predecessor

- Parent [M4-1g Draft PR #56](https://github.com/nalkarowndal/tyrfghx/pull/56),
  commit `a500fb3b6be55bbbdcdf361d705560d5d5cf6d90`.
- [General CI #39241708707](https://github.com/nalkarowndal/tyrfghx/actions/runs/39241708707)
  reports 4/4 success (frontend/Node, Python Linux, Python Windows,
  Windows Rust) on the predecessor's exact head.
- The long M2/M3/M4 Draft stack remains **not merged into main**.
  Production-release acceptance and owner approval are outstanding.

## New M4-1h code and tests

`src-tauri/src/native_fixture_handle_qa.rs` is included under
`#[cfg(all(test, windows))]` ONLY. Normal Tauri builds do not compile
it, and it adds **no** Tauri command, FastAPI route, shell sidecar,
GPU operation, downloaded file, model read, permission grant or
inference-worker action. Windows tests run in standard locked
`cargo test --lib --locked` CI.

The test harness creates **small synthetic temporary files** and
opens their metadata with Win32 `CreateFileW` using
`FILE_FLAG_OPEN_REPARSE_POINT` and
`FILE_FLAG_BACKUP_SEMANTICS` for the test directory.
It obtains `FILE_ATTRIBUTE_TAG_INFO` from
`GetFileInformationByHandleEx` and rejects reparse-point
or unexpected directory/file types. It also uses
`GetFinalPathNameByHandleW` to compare a fixed test child's final
handle path with its temporary root handle path. All opened native
handles close through RAII.

Unit tests cover:
- Synthetic regular fixture and a fixed marker under a fresh tempdir;
- Denied unapproved/traversal basenames, missing children and
  relative fixture directories;
- Denied child file symlinks and directory symlink aliases
  where Windows runners grant creation permission;
- No opens/reads of actual user model files, package caches,
  checkpoints, installed Python environments or production directories.

The only permitted child basenames in the test helper are
`sample.whl` and `fixture.marker`. Hashes, wheel structure,
signature trust and source provenance are **not** checked by this
Win32 module; prior M4-1e through M4-1g modules validate
separate synthetic-only sample data.

## Explicit security limitations

This is NOT a complete safe-native-path implementation, and no
production path safety result is returned. Although the final root
and child are opened with `OPEN_REPARSE_POINT` and checked by handle,
this fixture test does **not** walk/open *each ancestor component*
as a pinned handle or guarantee safe object identity under a
malicious concurrent directory swap. Windows filesystem redirects,
device namespaces, hardlinks, ACL policy, protected paths and network
shares require separate design review, validation and tests.
Matching a user-provided SHA-256 to actual bytes is also insufficient
to establish trusted provenance.

Before **real package** operations, separately implement a user-approved
native path-selection boundary with handle-relative, component-wise
Win32 resolution and caller authorization, verify installation source
provenance and all transitive hashes, acquire explicit install approval,
then request independent consent before GPU/CUDA diagnostics or model
loading. Do not promote this limited test to a production helper as-is.

## Acceptance gates

- [ ] Exact-head locked Windows Rust tests pass including new fixture cases.
- [ ] Exact-head Linux Python, Windows Python, frontend/Node tests pass.
- [ ] Production Tauri command list, permissions, read-only Python
  backend, release GPU flags, package installer and model paths unchanged.
- [ ] PR remains Draft and upstream Draft stack is owner-reviewed.

References:
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew
- https://docs.rs/windows-sys/0.61.2/windows_sys/Win32/Storage/FileSystem/index.html
- https://v2.tauri.app/security/capabilities/
