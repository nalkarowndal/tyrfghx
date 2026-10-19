# M4-1g — Strict tiny synthetic ZIP framing QA

## Existing verified baseline

M4-1f [Draft PR #55](https://github.com/nalkarowndal/tyrfghx/pull/55),
parent SHA `36786a12b8175310cd7030973fe88516ff6e5e5b`, passed
[general CI #39240394191](https://github.com/nalkarowndal/tyrfghx/actions/runs/39240394191)
(4/4: frontend, Linux Python, Windows Python, Windows Rust).
The earlier M2/M3/M4 Draft PR chain remains **unmerged** and requires
explicit human review before release or production integration.

## What is newly implemented

`backend/synthetic_zip_layout_preview.py` performs a bounded independent
framing check for **small in-memory synthetic fixtures only**, ahead of
the earlier `backend/synthetic_wheel_archive_preview.py` metadata/RECORD
validator. It does not read paths, packages or user files.

The check enforces:

- One classic, 22-byte **terminal End of Central Directory** (EOCD);
  no comment, prefix stub, trailing data, duplicate EOCD, multivolume ZIP
  or ZIP64 structures.
- Three to 32 central directory records, contiguous and exactly covering
  their declared central directory size.
- One-to-one agreement between the central directory and local header
  filename bytes, version-needed, flags, compression, DOS timestamps,
  CRC-32, compressed and uncompressed file sizes.
- Local file records begin at offset zero, do not overlap, and end exactly
  where the central directory begins. Reject gaps and masquerading
  appended payloads.
- No extra fields, per-entry archive comments or data descriptors. Accept
  only plain synthetic STORE/DEFLATE members with ASCII names and zero flags.
- Fixed upper size limit of **1 MiB for the entire byte input**,
  no execution, extraction or files opened. Existing archive checker still
  applies tight decompression and RECORD SHA-256 limits.

The integrated M4-1f result now includes
`synthetic_local_central_framing_match=true` only when all above
preconditions and the earlier metadata/RECORD checks succeed.
It still explicitly reports
`archive_parser_ambiguity_excluded=false` and
`production_install_authorized=false`.

## What this does NOT prove

This is a deliberately restrictive test of *one simple ZIP subset*,
not a general secure ZIP parser, or compatibility validation for real
PyPI wheels. Some legitimate modern wheels use ZIP features unsupported
here. This does **not** verify wheel provenance, publisher signing,
reviewed build reproducibility, transitive requirements, official
Torch/CUDA wheels, production Windows handle/path safety, user consent,
package installation, GPU readiness or AI generation.

In addition to the tests here, a future production design must use a
maintained/reviewed archive parser, strict authority/trust checks for
verified hashes and signature provenance, and native Win32 handle-based
path controls for user-selected paths. PyPI documented local/central
header confusion, duplicate filenames, extra end-records and ZIP overlays
in its 2025 security guidance; treat this preview as **negative regression
QA** only.

## Validation gates

- [ ] Exact branch-head frontend/Node, Linux Python, Windows Python and
  Windows Rust locked CI jobs all pass.
- [ ] Negative tests for divergent local/central names, CRC and sizes,
  wrong central offsets, multiple EOCDs, prefixes, appended data and
  unsupported extras pass on Linux and Windows.
- [ ] No Tauri command/permissions, FastAPI endpoint, model access,
  downloader, pip, runtime installation or GPU probing introduced.
- [ ] Keep Draft and await review/approval of stacked upstream PRs.

## Sources

- https://blog.pypi.org/posts/2025-08-07-wheel-archive-confusion-attacks/
- https://packaging.python.org/en/latest/specifications/binary-distribution-format/
- https://docs.python.org/3/library/zipfile.html
- https://v2.tauri.app/security/capabilities/
