"""M3-45 dependency inventory regression and safety tests (CPU-only/offline)."""
from importlib import metadata
import json

from runtime_preflight import PACKAGES, dependency_inventory


def test_everything_missing_is_not_verified():
    def absent(name):
        raise metadata.PackageNotFoundError(name)

    data = dependency_inventory(absent)
    assert data["readiness"] == "not_verified"
    assert data["method"] == "distribution_metadata_only"
    assert data["cuda_tested"] is False
    assert data["gpu_accessed"] is False
    assert data["models_opened"] is False
    assert data["downloads_performed"] is False
    assert [entry["package"] for entry in data["packages"]] == list(PACKAGES)
    assert all(entry == {"package": name, "state": "missing", "version": None}
               for name, entry in zip(PACKAGES, data["packages"]))


def test_all_dependencies_installed_still_not_gpu_ready():
    called = []

    def get_version(name):
        called.append(name)
        return "2.9.1+cu129" if name == "torch" else "0.38.2"

    data = dependency_inventory(get_version)
    assert called == list(PACKAGES)
    assert all(item["state"] == "detected" for item in data["packages"])
    assert data["packages"][0]["version"] == "2.9.1+cu129"
    assert data["readiness"] == "not_verified"
    assert not data["cuda_tested"] and not data["gpu_accessed"]
    json.dumps(data)


def test_untrusted_version_metadata_is_never_echoed_or_treated_as_present():
    dangerous = ["\nTOKEN=secret", "2.0\r\nInjection:yes", "a" * 1000, "../private/path", "", 7, None]
    for version in dangerous:
        data = dependency_inventory(lambda _: version)
        assert all(x["state"] == "unknown" and x["version"] is None
                   for x in data["packages"])
        assert json.dumps(data).find("secret") == -1
    assert dependency_inventory(lambda _: (_ for _ in ()).throw(OSError("secret local path")))["packages"][0]["state"] == "unknown"


def test_missing_one_dependency_does_not_reveal_unbounded_system_packages():
    def lookup(name):
        if name == "diffusers":
            raise metadata.PackageNotFoundError(name)
        return "0.1.0"

    data = dependency_inventory(lookup)
    assert len(data["packages"]) == len(PACKAGES)
    assert data["packages"][1] == {"package": "diffusers", "state": "missing", "version": None}
    assert data["readiness"] == "not_verified"


def test_status_api_is_metadata_only_and_without_any_model_execution(monkeypatch):
    import runtime_preflight
    from fastapi.testclient import TestClient
    from app import create_app

    observed = []
    def fake_version(name):
        observed.append(name)
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(runtime_preflight.metadata, "version", fake_version)
    # The status handler owns a direct callable default bound at definition
    # time: verify the JSON invariant, independent of local Python packages.
    with TestClient(create_app()) as client:
        result = client.get("/api/status")
    assert result.status_code == 200
    data = result.json()
    assert data["runtime_preflight"]["readiness"] == "not_verified"
    assert data["runtime_preflight"]["cuda_tested"] is False
    assert data["runtime_preflight"]["models_opened"] is False
    assert all(engine["status"] == "unavailable" for engine in data["engines"])
