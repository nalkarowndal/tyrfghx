"""M3-25 synthetic fixture: safe registration-only smoke coverage (no GPU)."""
import json
from pathlib import Path

import pytest

from qa_fixture import create_qa_fixture


def test_fixture_has_bounded_header_and_cannot_silently_overwrite(tmp_path: Path):
    path = tmp_path / "qa-m3-25.safetensors"
    written = create_qa_fixture(path)
    original = path.read_bytes()
    assert written == len(original) < 1024
    n = int.from_bytes(original[:8], "little")
    assert 0 < n < 1_048_576
    header = json.loads(original[8 : 8 + n])
    assert "NOT A REAL MODEL" in header["__metadata__"]["modelspec.title"]
    assert original[8 + n :] == b"\x00\x01\x02\x03"
    with pytest.raises(FileExistsError):
        create_qa_fixture(path)
    assert path.read_bytes() == original


def test_fixture_refuses_non_safetensors_path(tmp_path: Path):
    with pytest.raises(ValueError):
        create_qa_fixture(tmp_path / "test.ckpt")
    with pytest.raises(ValueError):
        create_qa_fixture(tmp_path / "test.txt")


def test_fixture_parent_safely_created(tmp_path: Path):
    path = tmp_path / "qa-output" / "sample.safetensors"
    assert not path.parent.exists()
    create_qa_fixture(path)
    assert path.is_file()


@pytest.mark.skipif(__import__("os").name == "nt", reason="Windows symlink privilege varies")
def test_fixture_rejects_symlink_parent(tmp_path: Path):
    target = tmp_path / "real"
    target.mkdir()
    alias = tmp_path / "link"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        create_qa_fixture(alias / "qa.safetensors")
    assert not (target / "qa.safetensors").exists()
