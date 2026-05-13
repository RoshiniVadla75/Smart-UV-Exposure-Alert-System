# Smart UV Exposure Alert System

A Flask web application for monitoring illuminance readings from a VEML6030 ambient light sensor connected to an IoT device such as an ESP32. The app receives lux readings, classifies the lighting condition, stores historical data, raises alerts for extreme conditions, and presents a responsive dashboard.

## What This Project Does

- Receives VEML6030 light readings through Bluetooth or API ingestion.
- Uses `lux` as the primary measurement unit.
- Classifies each reading as `Too Dark`, `Dim`, `Ideal`, `Bright`, or `Very Bright`.
- Stores readings and threshold events in SQLite.
- Provides one focused dashboard page.
- Pulls live Perth weather data for temperature, condition, humidity, wind, cloud cover, UV, sunrise, sunset, and forecast cards.
- Supports demo mode with automatic synthetic light readings.
- Includes API key protection, basic rate limiting, security headers, tests, and Docker support.

## Tech Stack

- Backend: Python, Flask, SQLite
- Frontend: Jinja2 templates, vanilla JavaScript, custom CSS
- Testing: Pytest
- Deployment: Gunicorn + Docker

## Light Level Rules

| Lux range | Level | Alert |
| --- | --- | --- |
| `< 50` | Too Dark | Yes |
| `50 - 499` | Dim | No |
| `500 - 4,999` | Ideal | No |
| `5,000 - 49,999` | Bright | No |
| `>= 50,000` | Very Bright | Yes |

The ingest API accepts lux values from `0` to `188000`, matching the configured VEML6030 operating range used by this app.

## Pages

- Dashboard: `/`

The dashboard uses separate pages for dashboard, live data, history, weather comparison, alerts, devices, settings, how it works, and project information.

The dashboard includes live lux, thresholds, buzzer state, OLED display preview, Bluetooth hardware status, exact location, recent readings, and a trend chart comparing VEML6030 lux with the location-based outdoor light estimate.

## Weather Comparison

Weather data is fetched through the Flask backend. If `WEATHER_API_KEY` is set, the app uses WeatherAPI. Without a key, it uses Open-Meteo for live Perth weather. The dashboard must not display hardcoded weather values as if they are live.

The comparison card combines live weather UV, daylight, cloud cover, and VEML6030 lux. If weather is unavailable, the UI says `Weather unavailable` instead of showing fake values.

To enable real weather with your own provider key:

1. Create `.env` in the project root.
2. Add `WEATHER_API_KEY=your_key_here`.
3. Restart the Flask app with `python run.py`.

## Backend API

- `GET /api/health`
- `POST /api/readings` protected with `X-API-Key` when configured
- `GET /api/readings/latest`
- `GET /api/readings/recent?limit=20`
- `GET /api/history?from=<iso>&to=<iso>`
- `GET /api/alerts`
- `GET /api/summary/today`
- `GET /api/weather?location=Perth, Australia`
- `GET /api/device-status`
- `GET /api/system/status`
- `POST /api/demo/start`
- `POST /api/demo/stop`
- `GET /api/demo/status`

## Quick Start

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a local `.env` file from `.env.example` and set values:

```env
PORT=5000
FLASK_DEBUG=false
INGEST_API_KEY=change-this-secret-key
DEMO_INTERVAL_SECONDS=5
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_MAX_REQUESTS=120
DEFAULT_WEATHER_LOCATION=Perth, Australia
WEATHER_API_KEY=your_key_here
WEATHER_API_TIMEOUT_SECONDS=4
```

Run the app:

```bash
export PORT=5000
export INGEST_API_KEY="change-this-secret-key"
python run.py
```

Open `http://localhost:5000/`.

## Bluetooth Hardware Setup

For the portable hardware setup, use Bluetooth Low Energy from the ESP32 to the browser. The browser acts as the local gateway: it connects to the ESP32 over BLE, receives VEML6030 lux packets, and forwards them to `POST /api/readings` so the dashboard, charts, alerts, and weather comparison update together.

Bluetooth is best for this version when the device is portable and the dashboard laptop/phone is nearby. Wi-Fi plus HTTP is better for unattended remote logging, but it requires network setup on the hardware. Classic Bluetooth serial can work, but browser support is poorer than BLE.

Recommended BLE profile:

| Item | Value |
| --- | --- |
| Device name prefix | `VEML`, `Light`, or `ESP32` |
| Service | Nordic UART Service |
| Service UUID | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify characteristic | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

The ESP32 should notify one newline-delimited packet every few seconds. Supported packet formats:

```json
{"device_id":"light-sensor-01","lux":850.5,"wifi_signal":-62}
```

```text
device_id=light-sensor-01,lux=850.5,wifi_signal=-62
```

```text
light-sensor-01,850.5,-62
```

Open the dashboard in Chrome or Edge on `localhost`, enter the ingest key if `INGEST_API_KEY` is configured, and press `Connect Bluetooth`. Web Bluetooth requires a secure context, and `localhost` is accepted for local development.

## API Hardware Payload

Bluetooth is the preferred path for the portable setup. You can still send readings from another controller or script to:

```text
POST /api/readings
```

Example JSON payload:

```json
{
  "device_id": "light-sensor-01",
  "lux": 850.5,
  "wifi_signal": -62,
  "timestamp": "2026-05-13T10:30:00Z",
  "source": "hardware"
}
```

`timestamp` is optional. If omitted, the server stores the current UTC time.

## Manual Smoke Test

Health:

```bash
curl -s http://localhost:5000/api/health
```

Ingest one reading:

```bash
curl -s -X POST http://localhost:5000/api/readings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-this-secret-key" \
  -d '{"device_id":"light-sensor-01","lux":850.5,"wifi_signal":-61,"source":"hardware"}'
```

Check latest reading:

```bash
curl -s http://localhost:5000/api/readings/latest
```

Toggle demo mode:

```bash
curl -s -X POST http://localhost:5000/api/demo/start
curl -s http://localhost:5000/api/demo/status
curl -s -X POST http://localhost:5000/api/demo/stop
```

## Testing

```bash
python -m pytest -q
```

The test suite validates health checks, protected ingestion, lux persistence, light-level classification, alert creation, invalid lux rejection, demo mode toggling, and VEML6030 status metadata.

## Run with Docker

Build image:

```bash
docker build -t veml6030-light-app .
```

Run container:

```bash
docker run --rm -p 5000:5000 \
  -e PORT=5000 \
  -e INGEST_API_KEY=change-this-secret-key \
  -e DEMO_INTERVAL_SECONDS=5 \
  -e RATE_LIMIT_WINDOW_SECONDS=60 \
  -e RATE_LIMIT_MAX_REQUESTS=120 \
  veml6030-light-app
```

## Project Structure

```text
VEML6030-Light-Sensor-Monitor/
|-- app/
|   |-- __init__.py            # app factory, security headers, rate limiting
|   |-- db.py                  # SQLite connection and schema initialization
|   |-- demo.py                # background demo lux generator
|   |-- routes.py              # HTML routes and REST API routes
|   |-- services.py            # light-level logic, timestamp parsing, persistence
|   |-- static/
|   |   |-- css/
|   |   |   `-- styles.css
|   |   `-- js/
|   |       |-- main.js
|   |       |-- dashboard.js
|   `-- templates/
|       |-- base.html
|       `-- index.html
|-- tests/
|   `-- test_app.py
|-- .env.example
|-- Dockerfile
|-- requirements.txt
|-- run.py
`-- README.md
```

## Operational Notes

- `POST /api/readings` requires `X-API-Key` when `INGEST_API_KEY` is set.
- App stores data in `instance/light_system.db` by default.
- Demo mode persists in `system_state.mode` and can auto-resume on restart.
- Rate limiting is in-memory and suited for a single app instance.
