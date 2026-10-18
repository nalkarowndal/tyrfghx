"""Hash every payload file, then verify the installed payload without changing it."""
import argparse
import hashlib
import json
from pathlib import Path


def snapshot(root):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink in bundle')
        if not path.is_file() or path == root / 'bundle-manifest.json':
            continue
        name = path.relative_to(root).as_posix()
        if any(part.casefold() in {'torch', 'diffusers', 'models', 'pytest'} for part in path.relative_to(root).parts):
            raise ValueError('unexpected inference/test payload')
        with path.open('rb') as stream:
            files[name] = {'size': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    if 'aiimage-backend.exe' not in files or not any(name.endswith('python312.dll') for name in files):
        raise ValueError('missing executable or embedded Python')
    with (root / 'aiimage-backend.exe').open('rb') as exe:
        if exe.read(2) != b'MZ':
            raise ValueError('invalid PE')
    return {'schema_version': 1, 'files': files}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    value = snapshot(args.root)
    manifest = args.root / 'bundle-manifest.json'
    if args.verify:
        if json.loads(manifest.read_text(encoding='utf-8')) != value:
            raise SystemExit('backend_bundle: payload_mismatch')
    else:
        manifest.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(f"backend_bundle: {'verified' if args.verify else 'recorded'} {len(value['files'])} files")
