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
    assert "bluetooth=(self)" in response.headers["Permissions-Policy"]


def test_post_and_get_latest_reading(client):
    unauthorized = client.post(
        "/api/readings",
        json={
            "device_id": "light-sensor-01",
            "lux": 750,
            "wifi_signal": -60,
            "source": "hardware",
        },
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/api/readings",
        headers={"X-API-Key": "test-key"},
        json={
            "device_id": "light-sensor-01",
            "lux": 750,
            "wifi_signal": -60,
            "source": "hardware",
        },
    )
    assert response.status_code == 201
    latest = client.get("/api/readings/latest")
    assert latest.status_code == 200
    latest_data = latest.get_json()
    assert latest_data["lux"] == 750
    assert latest_data["light_level"] == "Ideal"
    assert latest_data["threshold_status"] == "Within Threshold"
    assert latest_data["buzzer_state"] == "OFF"
    assert "Lux 750.0" in latest_data["oled_message"]


def test_extreme_light_reading_creates_alert(client):
    response = client.post(
        "/api/readings",
        headers={"X-API-Key": "test-key"},
        json={
            "device_id": "light-sensor-01",
            "lux": 30,
            "wifi_signal": -57,
            "source": "hardware",
        },
    )
    assert response.status_code == 201
    data = response.get_json()["reading"]
    assert data["light_level"] == "Too Dark"

    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    alert_data = alerts.get_json()
    assert alert_data[0]["lux"] == 30
    assert alert_data[0]["light_level"] == "Too Dark"


def test_rejects_invalid_lux_range(client):
    response = client.post(
        "/api/readings",
        headers={"X-API-Key": "test-key"},
        json={
            "device_id": "light-sensor-01",
            "lux": 250000,
            "source": "hardware",
        },
    )
    assert response.status_code == 400
    assert "lux" in response.get_json()["error"]


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


def test_system_status_reports_veml6030(client):
    response = client.get("/api/system/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["sensor_info"]["sensor"] == "VEML6030"
    assert data["sensor_info"]["measurement"] == "Illuminance (lux)"


def test_weather_route_uses_configured_adapter(client, monkeypatch):
    def fake_weather(location, timeout, latitude=None, longitude=None):
        return {
            "source": "test",
            "status": "ok",
            "location": {"label": location, "latitude": latitude, "longitude": longitude},
            "current": {
                "temperature_c": 22,
                "cloud_cover_percent": 30,
                "shortwave_radiation_w_m2": 500,
            },
            "daily": {},
            "hourly": [],
            "timeout": timeout,
        }

    monkeypatch.setattr("app.routes.fetch_weather_summary", fake_weather)
    response = client.get("/api/weather?location=Perth")
    assert response.status_code == 200
    data = response.get_json()
    assert data["location"]["label"] == "Perth"
    assert data["current"]["shortwave_radiation_w_m2"] == 500


def test_reading_accepts_location_metadata(client):
    response = client.post(
        "/api/readings",
        headers={"X-API-Key": "test-key"},
        json={
            "device_id": "light-sensor-01",
            "lux": 1200,
            "source": "hardware",
            "location_label": "Perth hardware field test",
            "latitude": -31.9523,
            "longitude": 115.8613,
        },
    )
    assert response.status_code == 201
    latest = client.get("/api/readings/latest").get_json()
    assert latest["location_label"] == "Perth hardware field test"
    assert latest["latitude"] == -31.9523
    assert latest["longitude"] == 115.8613
