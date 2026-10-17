from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_health():
    assert client.get("/api/health").json() == {"ok": True}

def test_status_truthful():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "aiimage"
    assert data["mode"] == "foundation"
    assert all(engine["status"] == "unavailable" for engine in data["engines"])
