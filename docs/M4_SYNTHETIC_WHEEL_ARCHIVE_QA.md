# M4-1f — in-memory synthetic Wheel archive structure QA

## Verified baseline and scope

The predecessor M4-1e [Draft PR #54](https://github.com/nalkarowndal/tyrfghx/pull/54)
at `c3485cb80250d19edbb6d34eb26c1bf5303b79e6` passed all four
general GitHub Actions CI jobs in
[run #39239150631](https://github.com/nalkarowndal/tyrfghx/actions/runs/39239150631).
The dependent M2/M3/M4 Draft PR stack remains **unmerged**. Neither this
work nor the earlier SHA-256 fixture checks authorizes a release, production
worker launch or any GPU/AI operation.

## Code delivered

`backend/synthetic_wheel_archive_preview.py` checks **in-memory synthetic
bytes** representing very small fake Wheels; it has no filesystem access.
The module uses only Python's standard library and does **not** extract,
execute, import, install, download or read real packages.

- Input must be `bytes` of at most 1 MiB, with one of two narrowly
  enumerated *sample* wheel tags:
  `cp312-cp312-win_amd64` or `py3-none-any`, and a package name from the
  project's six-name metadata inventory. **This is not full PEP 425/427
  tag compatibility resolution.**
- ZIP central-directory entries: 3–32 files, maximum 1 MiB each,
  4 MiB combined advertised decompressed size; only STORE/DEFLATE;
  reject encrypted/data-descriptor entries, directories, Unix symlink
  and other special file modes, duplicate or case-folded-colliding names,
  Windows device aliases, non-ASCII names, absolute paths, dot segments,
  separators/ADS and suspicious compression ratios.
- Requires the filename-matched `*.dist-info/WHEEL`,
  `METADATA` and `RECORD` members; checks a restricted sample
  `Wheel-Version: 1.0`, purelib flag, tag, metadata name and version.
- Parses RECORD as a strict 3-column CSV, requires each archive member
  exactly once, checks per-entry byte length and SHA-256 base64url digests,
  with no digest for RECORD itself.
- Synthetic tests generate mock ZIPs in memory and cover malformed,
  truncated, wrong-tag, path traversal, duplicate/casefold, altered hashes,
  bad metadata and high compression-ratio inputs.
- A small test also composes the earlier M4-1e synthetic file SHA gate
  with this new byte-level structure checker using a disposable `tmp_path`
  fixture. It never opens real user models, LoRAs or wheel caches.

## Explicit limitations

This is **only a narrow heuristic preview for synthetic QA**.
Zipfile parsing alone cannot rule out all ZIP parser confusion attacks:
local header/central directory mismatches, appended data, extra EOCD
records and discrepancies between Python ZIP parsers and other installers
remain unverified. It does not establish PyPI signing, source trust,
license review, full dependency closure, supported Torch/CUDA versions,
safe real-world filesystem paths or actual installability. Production
compatibility, source provenance, signature verification and install
authorization remain **false** even after a passing synthetic fixture.

Before testing any real user-selected Wheel, implement separately reviewed
native Windows handle-based path and reparse safety, authoritative wheel
provenance and signatures where available, an explicit trusted hash-pinned
lockfile including transitive dependencies, and a parser capable of
rejecting ambiguous ZIP structure. Actual installation/GPU device
probing requires a separate explicit user decision.

## Acceptance gates

- [ ] Exact-head frontend+Node, Linux Python, Windows Python and locked
  Windows Rust jobs all succeed.
- [ ] No Python subprocess, Tauri command/permission, installer,
  package download, CUDA inference or FastAPI endpoint introduced.
- [ ] Keep Draft PR stacked on M4-1e until authorized upstream integration.

## References

- [Binary distribution format (PyPA)](https://packaging.python.org/en/latest/specifications/binary-distribution-format/)
- [Wheel / PEP 427](https://peps.python.org/pep-0427/)
- [PyPI ZIP parser confusion mitigations](https://blog.pypi.org/posts/2025-08-07-wheel-archive-confusion-attacks/)
- [Tauri 2 capabilities](https://v2.tauri.app/security/capabilities/)
