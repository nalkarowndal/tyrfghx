# M3-15 — private stdin JSON protocol for user-approved SDXL jobs

This milestone hardens the **existing Windows Tauri DEBUG-only** CUDA
generation worker from M3-14. It does not enable GPU inference in
release builds, web browsers or any network-facing API.

## Security problem

Previously the Rust process launched the fixed local Python
backend/generate_sdxl.py script with --checkpoint, --prompt and
--negative-prompt values as **process command-line arguments**.
Even without a shell, this had two weaknesses:

1. On Windows, ordinary process inspection/debugging can expose the
   executable command line, including the user's private prompt.
2. argparse can treat a negative-looking prompt (one beginning with
   a dash) as an option, rejecting otherwise valid user input.

This milestone moves all variable generation settings into a tightly
bounded private stdin pipe after the existing **Windows Job Object is
created and the Python process is attached**. The process command line
now contains only the checked fixed Python executable, the fixed
backend script and three fixed switches:

    -s backend/generate_sdxl.py --request-stdin --execute --metrics

The private JSON includes checkpoint identifier, prompt, negative
prompt, dimensions, step count, CFG guidance and seed. It is neither
logged nor written to a temporary command-parameter file. No general
command execution or configurable Python path is introduced.

## Protocol contract

- The Rust serializer produces **schema_version = 1**, exact predefined
  camelCase setting keys, and a UTF-8 JSON object capped at **32 KiB**.
- The Python CLI reads at most 32 KiB + 1 byte from sys.stdin.buffer.
  Empty, truncated, malformed UTF-8/JSON and oversized messages fail.
- Unexpected/missing keys, duplicate JSON keys, non-standard JSON
  NaN/Infinity, booleans in numeric fields and unknown versions fail.
- The existing GenerationSettings class checks registered checkpoint
  IDs, prompt length, dimensions, steps, guidance and seed before any
  model load.
- --request-stdin requires **both --execute and --metrics**. It rejects
  simultaneous --prompt, --checkpoint or numeric CLI arguments rather
  than picking one input source. No arbitrary file paths or executable
  names can appear in the stdin schema.
- The Rust worker serializes and rejects oversized input **before**
  starting the subprocess. Once the supervised child exists, a
  dedicated short-lived writer sends the bounded request through
  stdin and closes the pipe. Backpressure cannot block the Tauri
  command or cancellation supervisor.
- The pre-existing 30-minute watchdog, kill-on-close Windows Job
  Object, independent GPU VRAM probe, explicit user approval, single
  active generation, bounded stdout/stderr collection and independent
  PNG decode/CRC/SHA-256 verification remain in force.

### Manual CLI compatibility

The standalone Python CLI keeps its original --checkpoint and
--prompt arguments (and dry-run behavior) for manual use. This change
protects **the Tauri-launched subprocess command line**, not commands
the owner deliberately types into a terminal. The read-only
hardware_acceptance.py workflow also remains separate.

## Automated validation

Rust unit tests prove a dash-leading Unicode prompt and private
negative prompt appear in the stdin payload but not the fixed
Command.get_args() list, and that oversized serialized messages are
rejected without spawning.

Python tests cover UTF-8, leading '-' prompts and newlines, strict
schema, duplicate/missing/unknown fields, NaN/Infinity, boolean
numeric fields, 32 KiB cap, CLI mixed-mode rejection, and an actual
CLI code path tested with injected fake inference and fake CUDA.
**No real model weights or CUDA GPU run in CI.**

## Limitations

Anonymous stdin reduces accidental *process command-line* disclosure.
It does NOT encrypt the bytes in process memory, guarantee total
endpoint privacy against privileged local attackers, or prevent
another process from capturing the OS/application memory. Nor does
it verify the artistic quality, speed, VRAM usage or cancellation
behavior of the actual RTX 2060 SUPER 8GB.

Real Windows GPU/visual acceptance remains required before merging.

References:
- Python argparse: https://docs.python.org/3/library/argparse.html
- Python json decoder: https://docs.python.org/3/library/json.html
- Rust std::process: https://doc.rust-lang.org/std/process/
- M3_GENERATION_FAILURE_RECOVERY.md
