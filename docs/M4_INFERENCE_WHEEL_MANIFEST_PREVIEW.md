# M4-1d — Offline inference wheel manifest preview (NO install)

## Verified prerequisites

- Parent CPU-only Win32 stdio QA [PR #52](https://github.com/nalkarowndal/tyrfghx/pull/52),
  SHA `c848af2b2ce704fd895341139a21c3b4edd0a78b`, passed all four
  routine CI jobs in [workflow #39235995868](https://github.com/nalkarowndal/tyrfghx/actions/runs/39235995868).
- M2/M3/M4 staged Draft chain is still NOT integrated or released. The next
  branch must not bypass the stack's security review and owner approval.

## What this slice actually implements

`backend/inference_install_preview.py` parses an **in-memory candidate
manifest only** (UTF-8 JSON <= 32 KiB) and returns a plain JSON-safe
estimate. It has no filesystem, network, pip, GPU, subprocess, or disk APIs.
`backend/test_inference_install_preview.py` exercises cancellation, invalid
frames, duplicate JSON keys, malformed versions and SHA-256 values, rejected
path/URL-like wheel names, unsupported names, size bounds and no-execution
outcomes under both Linux and Windows Python CI.

Manifest format (illustrative synthetic data; **not** a real wheel hash):

```json
{
  "schema_version": 1,
  "platform": "windows_x86_64",
  "python_version": "3.12",
  "destination_kind": "user_selected_private_venv",
  "wheels": [
    {
      "package": "torch",
      "version": "2.6.0+cu124",
      "filename": "torch-2.6.0+cu124-cp312-cp312-win_amd64.whl",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "declared_bytes": 125000000
    }
  ]
}
```

Only one wheel record per name is allowed; names are limited to the
fixed dependency inventory `torch, diffusers, transformers, accelerate,
safetensors, pillow`. All versions must be exact pinned strings; no
`>=`/pip argument or shell syntax is accepted. Filenames are checked
for a narrow wheel-style syntax but do **not** constitute validated wheel
tags or binary identity. SHA-256 fields are checked for **format only**.

No target path can appear in the manifest: `destination_kind` is
only a declared conceptual choice, **not** proof the user has chosen
a real path or that it is safe. In a later explicitly approved
integration step, native path validation MUST reject symlinks, junctions,
reparse points, canonicalization races, protected directories, and
connections to the frozen bundled FastAPI Python environment.

## Storage preview limitations

The displayed provisional budget is
`3 * sum(unverified_declared_bytes) + 2 GiB`. This is a **planning
heuristic**, not a measured installation requirement, disk occupancy,
or memory demand. `available_bytes`, when supplied, is injected test
metadata and not an actual disk probe. Even `reported_sufficient_unverified`
never permits any action. The result always reports:
`blocked_pending_explicit_approval`, false for hash verification,
provenance, dependency resolution, runtime compatibility, target path
inspection, GPU checks, download, install, and execution.

A cancellation flag produces a constant `cancelled` response without
parsing untrusted bytes. Invalid options and input fail closed with
fixed error codes without echoing filenames, digests, paths or inputs.

## Prerequisites for any future actual installer

1. Obtain explicit user consent for the actual *location* and separate
   OS-managed runtime, and enforce secure native canonical path/permissions
   against real filesystem state. Keep the frozen read-only backend untouched.
2. Select a Python 3.12 interpreter by trusted absolute path with pinned
   provenance, not from an arbitrary `PATH` entry.
3. Resolve the **complete transitive dependency set**, compare official
   compatible Windows/Python/CPU/CUDA wheels, and pin verified SHA-256
   hashes using a reviewed locked wheel manifest. Current optional
   `backend/requirements-inference.txt` contains ranges and is **not**
   a deployable hash-pinned lockfile.
4. Verify actual wheel bytes in a staged isolated directory, atomic
   installation and rollback, access permissions, disk capacity,
   package signing/provenance, cancellation and Windows Job Object
   ownership. These operations require a different explicitly authorized
   development phase, not this code.
5. Separately request user approval before GPU probing, Torch/CUDA,
   weight loading or sample image inference.

## Acceptance

- [ ] New exact-head frontend, Linux/Windows Python and Windows Rust CI 4/4 success.
- [ ] No new Tauri command/permission, Windows installer, download,
  venv creation, FastAPI endpoint, or GPU release flag.
- [ ] PR remains Draft; owner reviews stacked dependencies before merge.

References: [Python venv](https://docs.python.org/3/library/venv.html),
[Python Packaging User Guide](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/),
[pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/),
[PyTorch official selector](https://pytorch.org/get-started/locally/),
[Tauri v2 capabilities](https://v2.tauri.app/security/capabilities/).
