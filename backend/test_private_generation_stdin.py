"""M3-15 private GUI request protocol: offline and CUDA-free deterministic tests."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import generate_sdxl


def valid_private_request(**overrides):
    return {
        "schema_version": 1,
        "checkpointId": "checkpoints/mock.safetensors",
        "prompt": "-negative-looking prompt 🌙 \n with a separate line",
        "negativePrompt": "low quality, blurry",
        "width": 512, "height": 512, "steps": 15,
        "guidance": 7.0, "seed": 42,
        **overrides,
    }


def read_payload(raw):
    return generate_sdxl.read_private_generation_request(io.BytesIO(raw))


def test_utf8_private_request_preserves_leading_dash_and_newlines():
    settings = read_payload(json.dumps(valid_private_request()).encode("utf-8"))
    assert settings.prompt.startswith("-negative-looking prompt")
    assert "🌙" in settings.prompt and "\n" in settings.prompt
    assert settings.checkpoint_id == "checkpoints/mock.safetensors"
    assert settings.negative_prompt == "low quality, blurry"


@pytest.mark.parametrize("value", [
    b"", b"garbage", b"[]", b"{}", b"\xff", b" " * (32 * 1024 + 1),
    b'{"schema_version":1,"schema_version":1}',
    b'{"a": NaN}', b'{"a": Infinity}',
], ids=[
    "empty", "invalid_text", "array", "object", "invalid_utf8",
    "oversize", "duplicate_key", "nan", "infinity",
])
def test_rejects_malformed_duplicate_and_oversized_private_data(value):
    with pytest.raises(ValueError):
        read_payload(value)


@pytest.mark.parametrize("overrides", [
    {"schema_version": 2},
    {"width": True},
    {"height": "512"},
    {"seed": -1},
    {"steps": 0},
    {"guidance": "7.0"},
    {"guidance": False},
    {"guidance": 100.0},
    {"checkpointId": "../../outside.safetensors"},
    {"prompt": ""},
    {"prompt": "x" * 2001},
    {"prompt": "한" * 2000},  # Valid codepoints; still < 32KiB after encoding.
])
def test_private_input_enforces_same_generation_settings(overrides):
    payload = json.dumps(valid_private_request(**overrides)).encode()
    if overrides == {"prompt": "한" * 2000}:
        assert read_payload(payload).prompt == overrides["prompt"]
    else:
        with pytest.raises(ValueError):
            read_payload(payload)


def test_unknown_key_and_missing_fields_are_rejected():
    obj = valid_private_request()
    obj["extra_shell_command"] = "cmd.exe"
    with pytest.raises(ValueError, match="schema"):
        read_payload(json.dumps(obj).encode())
    del obj["extra_shell_command"]
    del obj["negativePrompt"]
    with pytest.raises(ValueError, match="schema"):
        read_payload(json.dumps(obj).encode())


def test_bounded_read_never_consumes_unlimited_stream():
    class Stream:
        def __init__(self):
            self.n = None

        def read(self, n):
            self.n = n
            return b"x" * n

    stream = Stream()
    with pytest.raises(ValueError, match="oversized"):
        generate_sdxl.read_private_generation_request(stream)
    assert stream.n == 32 * 1024 + 1


def test_stdin_mode_requires_execute_and_metrics_without_model_loading():
    for argv in [
        ["--request-stdin"],
        ["--request-stdin", "--execute"],
        ["--request-stdin", "--metrics"],
        ["--request-stdin", "--execute", "--metrics", "--prompt", "leak"],
        ["--request-stdin", "--execute", "--metrics", "--checkpoint", "checkpoints/mock.safetensors"],
    ]:
        with pytest.raises(SystemExit) as error:
            generate_sdxl.main(argv)
        assert error.value.code == 2


def test_actual_stdin_cli_path_uses_strict_request_not_argv(monkeypatch, tmp_path, capsys):
    payload = valid_private_request()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
        io.BytesIO(json.dumps(payload).encode()), encoding="utf-8"
    ))
    called = {}

    def stub_preflight(settings):
        called["preflight"] = settings.prompt
        return tmp_path, tmp_path, SimpleNamespace(config_found=True)

    def stub_inference(settings):
        called["inference"] = settings.prompt
        png = tmp_path / "synthetic_fixture_only.png"
        png.write_bytes(b"NOT A REAL PNG; no actual GPU or model run")
        return png

    monkeypatch.setattr(generate_sdxl, "prepare_generation", stub_preflight)
    monkeypatch.setattr(generate_sdxl, "run_generation", stub_inference)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False)
    ))
    result = generate_sdxl.main(["--request-stdin", "--execute", "--metrics"])
    assert result == 0
    assert called["preflight"] == payload["prompt"]
    assert called["inference"] == payload["prompt"]
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "generated_unverified"
    assert output["metrics"]["gpu_memory_measurement"] == "unavailable"
    assert payload["prompt"] not in json.dumps(output)
