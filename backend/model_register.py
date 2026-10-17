"""Explicit local command-line registration for annotations (no network API writes)."""
from __future__ import annotations

import argparse
from pathlib import Path

from model_metadata import ModelAnnotation, save_annotation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register descriptive metadata for an existing aiimage model.")
    parser.add_argument("model_id", help="e.g. checkpoints/example.safetensors")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent / "models")
    parser.add_argument("--name", dest="display_name")
    parser.add_argument("--family", choices=["sd15", "sd2", "sdxl", "sd3", "flux"], dest="family_override")
    parser.add_argument("--license")
    parser.add_argument("--notes")
    args = parser.parse_args(argv)
    try:
        annotation = ModelAnnotation(
            display_name=args.display_name, family_override=args.family_override,
            license=args.license, notes=args.notes,
        )
        save_annotation(args.root, args.model_id, annotation)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Saved annotation for {args.model_id}. Metadata hints do not prove compatibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
