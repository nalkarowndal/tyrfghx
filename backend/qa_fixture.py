"""M3-25: create a tiny OFFLINE QA-only safetensors-header fixture.

This contains no tensors and CANNOT generate an image. Run deliberately on
the operator's machine to exercise native Tauri import/catalog/hash UI without
downloading real models. The output is excluded by .gitignore.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "qa-fixtures" / "m3-25-ui.safetensors"


def create_qa_fixture(path: Path) -> int:
    if path.suffix.lower() != ".safetensors" or path.name in {"", ".", ".."}:
        raise ValueError("Expected a .safetensors fixture filename")
    if path.parent.is_symlink():
        raise ValueError("Fixture directory must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError("Unsafe fixture directory")
    header = json.dumps(
        {"__metadata__": {"modelspec.title": "M3-25 synthetic QA fixture - NOT A REAL MODEL"}},
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    # Header-only inventory fixture, deliberately *not* valid model weights.
    content = len(header).to_bytes(8, "little") + header + bytes([0, 1, 2, 3])
    # Exclusive creation: never silently overwrite any operator file.
    with path.open("xb") as handle:
        handle.write(content)
    return len(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a tiny, non-inference model-manager UI QA fixture")
    parser.add_argument("--output", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()
    try:
        size = create_qa_fixture(args.output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"QA fixture creation refused: {type(error).__name__}\n")
    print(f"M3-25 QA fixture created ({size} bytes). NOT a model; never use for GPU generation.")
    print("Use the Tauri model-import file selector to select the generated .safetensors file.")


if __name__ == "__main__":
    main()
