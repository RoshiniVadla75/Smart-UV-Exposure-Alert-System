import tempfile

import pytest

from app import create_app


@pytest.fixture()
def client():
    db_file = tempfile.NamedTemporaryFile(delete=False)
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": db_file.name,
            "INGEST_API_KEY": "test-key",
            "RATE_LIMIT_MAX_REQUESTS": 1000,
        }
    )
    with app.test_client() as client:
        yield client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["backend"] == "ok"
    assert data["database"] == "ok"


def test_post_and_get_latest_reading(client):
    unauthorized = client.post(
        "/api/readings",
        json={
            "device_id": "uv-station-01",
            "uv_index": 2.5,
            "wifi_signal": -60,
            "source": "hardware",
        },
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/api/readings",
        headers={"X-API-Key": "test-key"},
        json={
            "device_id": "uv-station-01",
            "uv_index": 2.5,
            "wifi_signal": -60,
            "source": "hardware",
        },
    )
    assert response.status_code == 201
    latest = client.get("/api/readings/latest")
    assert latest.status_code == 200
    latest_data = latest.get_json()
    assert latest_data["risk_level"] == "Low"


def test_invalid_limit(client):
    response = client.get("/api/readings/recent?limit=0")
    assert response.status_code == 400


def test_demo_status_and_toggle(client):
    status_before = client.get("/api/demo/status")
    assert status_before.status_code == 200
    assert status_before.get_json()["mode"] == "hardware"

    started = client.post("/api/demo/start")
    assert started.status_code == 200
    status_after = client.get("/api/demo/status")
    assert status_after.status_code == 200
    assert status_after.get_json()["mode"] == "demo"

    stopped = client.post("/api/demo/stop")
    assert stopped.status_code == 200
