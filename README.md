# Smart UV Exposure Alert System

A full-stack Flask web application for monitoring UV index readings from an IoT device (or demo simulator), classifying risk levels, storing historical data, and presenting a user-friendly dashboard for public monitoring.

## What This Project Does

- Receives UV sensor readings through API ingestion.
- Classifies each reading as `Low`, `Moderate`, or `High` risk.
- Stores readings and alerts in SQLite.
- Provides multi-page UI for dashboard, live stream, history, alerts, and device status.
- Supports demo mode with automatic background reading generation.
- Includes public-use baseline hardening: API key protection, rate limiting, security headers, tests, and Docker.

## Tech Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** Jinja2 templates, vanilla JavaScript, custom CSS
- **Testing:** Pytest
- **Deployment:** Gunicorn + Docker

## Features

### Frontend

- Interactive modern UI with responsive layout and hover/focus states.
- Pages:
  - Dashboard (`/`)
  - Live Data (`/live-data`)
  - History (`/history`)
  - Alerts (`/alerts`)
  - Devices (`/devices`)

### Backend API

- `GET /api/health`
- `POST /api/readings` (protected with `X-API-Key` when configured)
- `GET /api/readings/latest`
- `GET /api/readings/recent?limit=20`
- `GET /api/readings/history?from=<iso>&to=<iso>`
- `GET /api/alerts`
- `GET /api/summary/today`
- `GET /api/device-status`
- `POST /api/demo/start`
- `POST /api/demo/stop`
- `GET /api/demo/status`

### Security and Reliability

- API key check on ingestion endpoint (`X-API-Key`).
- Basic per-IP rate limiting for API endpoints.
- Security headers: CSP, no-sniff, frame deny, referrer policy, permissions policy.
- Centralized timestamp parsing and validation.
- Background demo engine for synthetic readings.

## Quick Start (Bash)

### 1) Create and activate virtual environment

```bash
python -m venv .venv
source .venv/Scripts/activate
```

If you are on Linux/macOS, use:

```bash
source .venv/bin/activate
```

### 2) Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3) Configure environment

Create a local `.env` file (copy from `.env.example`) and set values:

```env
PORT=5000
FLASK_DEBUG=false
INGEST_API_KEY=change-this-secret-key
DEMO_INTERVAL_SECONDS=5
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_MAX_REQUESTS=120
```

### 4) Run the app

```bash
export PORT=5000
export INGEST_API_KEY="change-this-secret-key"
python run.py
```

Open in browser:

- `http://localhost:5000/`
- `http://localhost:5000/live-data`
- `http://localhost:5000/history`
- `http://localhost:5000/alerts`
- `http://localhost:5000/devices`

## Testing the App

### Automated tests

```bash
python -m pytest -q
```

Current suite validates:

- health endpoint response
- secure ingestion behavior (authorized/unauthorized)
- risk classification persistence
- input validation (`limit`)
- demo mode status/toggle flow

### Manual smoke test (API)

#### Health

```bash
curl -s http://localhost:5000/api/health
```

#### Ingest one reading

```bash
curl -s -X POST http://localhost:5000/api/readings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-this-secret-key" \
  -d '{"device_id":"uv-station-01","uv_index":5.2,"wifi_signal":-61,"source":"hardware"}'
```

#### Check latest reading

```bash
curl -s http://localhost:5000/api/readings/latest
```

#### Toggle demo mode

```bash
curl -s -X POST http://localhost:5000/api/demo/start
curl -s http://localhost:5000/api/demo/status
curl -s -X POST http://localhost:5000/api/demo/stop
```

## Run with Docker

Build image:

```bash
docker build -t smart-uv-app .
```

Run container:

```bash
docker run --rm -p 5000:5000 \
  -e PORT=5000 \
  -e INGEST_API_KEY=change-this-secret-key \
  -e DEMO_INTERVAL_SECONDS=5 \
  -e RATE_LIMIT_WINDOW_SECONDS=60 \
  -e RATE_LIMIT_MAX_REQUESTS=120 \
  smart-uv-app
```

## Project Structure

```text
Smart-UV-Exposure-Alert-System/
├── app/
│   ├── __init__.py            # app factory, security headers, rate limiting, startup behavior
│   ├── db.py                  # SQLite connection + schema initialization
│   ├── demo.py                # background demo reading generator
│   ├── routes.py              # HTML routes + REST API routes
│   ├── services.py            # risk logic, timestamp parsing, reading persistence
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css     # interactive styling
│   │   └── js/
│   │       ├── main.js
│   │       ├── dashboard.js
│   │       ├── live-data.js
│   │       ├── history.js
│   │       ├── alerts.js
│   │       └── devices.js
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── live-data.html
│       ├── history.html
│       ├── alerts.html
│       └── devices.html
├── tests/
│   └── test_app.py            # pytest API tests
├── .env.example               # environment variable template
├── .gitignore
├── Dockerfile
├── requirements.txt
├── run.py                     # app entrypoint
└── README.md
```

## Operational Notes

- `POST /api/readings` requires `X-API-Key` when `INGEST_API_KEY` is set.
- App stores data in `instance/uv_system.db`.
- Demo mode persists in DB (`system_state.mode`) and can auto-resume on restart.
- Rate limiting is in-memory (suitable for single-instance deployments).

## Next Production Improvements (Optional)

- Move to persistent/shared rate limiting (Redis) for multi-instance deployments.
- Add user authentication + RBAC for admin actions.
- Add CI pipeline (lint, test, build, security checks).
- Add HTTPS reverse proxy (Nginx) and managed secrets.
