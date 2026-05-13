from datetime import datetime, timedelta, timezone

from flask import current_app, jsonify, redirect, render_template, request, url_for

from .db import get_db
from .services import (
    HIGH_LIGHT_THRESHOLD_LUX,
    LOW_LIGHT_THRESHOLD_LUX,
    now_iso,
    parse_iso_timestamp,
    persist_reading,
)
from .weather import fetch_weather_summary


def _validate_payload(payload):
    if not isinstance(payload, dict):
        return "Payload must be a JSON object."
    if not payload.get("device_id") or not isinstance(payload.get("device_id"), str):
        return "device_id is required and must be a string."
    lux = payload.get("lux")
    try:
        lux = float(lux)
    except (TypeError, ValueError):
        return "lux is required and must be a number."
    if lux < 0 or lux > 188000:
        return "lux must be between 0 and 188000 (VEML6030 range)."
    latitude = payload.get("latitude")
    if latitude not in (None, ""):
        try:
            latitude = float(latitude)
        except (TypeError, ValueError):
            return "latitude must be a number when provided."
        if latitude < -90 or latitude > 90:
            return "latitude must be between -90 and 90."
    longitude = payload.get("longitude")
    if longitude not in (None, ""):
        try:
            longitude = float(longitude)
        except (TypeError, ValueError):
            return "longitude must be a number when provided."
        if longitude < -180 or longitude > 180:
            return "longitude must be between -180 and 180."
    location_label = payload.get("location_label")
    if location_label is not None and not isinstance(location_label, str):
        return "location_label must be a string when provided."
    wifi = payload.get("wifi_signal")
    if wifi is not None:
        try:
            int(wifi)
        except (TypeError, ValueError):
            return "wifi_signal must be an integer when provided."
    source = payload.get("source", "hardware")
    if source not in ("hardware", "demo"):
        return "source must be either 'hardware' or 'demo'."
    timestamp = payload.get("timestamp")
    if timestamp is not None and parse_iso_timestamp(timestamp) is None:
        return "timestamp must be a valid ISO datetime when provided."
    return None


def register_routes(app):
    @app.get("/")
    def dashboard_page():
        return render_template("index.html")

    @app.get("/live-data")
    def live_data_page():
        return redirect(url_for("dashboard_page"))

    @app.get("/history")
    def history_page():
        return redirect(url_for("dashboard_page"))

    @app.get("/alerts")
    def alerts_page():
        return redirect(url_for("dashboard_page"))

    @app.get("/devices")
    def devices_page():
        return redirect(url_for("dashboard_page"))

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "backend": "ok",
                "database": "ok",
                "timestamp": now_iso(),
            }
        )

    @app.post("/api/readings")
    def post_reading():
        required_key = current_app.config.get("INGEST_API_KEY", "")
        if required_key:
            provided_key = request.headers.get("X-API-Key", "")
            if provided_key != required_key:
                return jsonify({"error": "Unauthorized ingestion key."}), 401

        payload = request.get_json(silent=True)
        error = _validate_payload(payload)
        if error:
            return jsonify({"error": error}), 400

        db = get_db()
        payload["timestamp"] = parse_iso_timestamp(payload.get("timestamp")) or now_iso()
        reading = persist_reading(db, payload)

        return (
            jsonify(
                {
                    "success": True,
                    "reading": reading,
                }
            ),
            201,
        )

    @app.get("/api/readings/latest")
    def get_latest():
        row = get_db().execute(
            "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return jsonify(dict(row) if row else None)

    @app.get("/api/readings/recent")
    def get_recent():
        limit = request.args.get("limit", default=20, type=int)
        if limit < 1 or limit > 500:
            return jsonify({"error": "limit must be between 1 and 500."}), 400
        rows = get_db().execute(
            "SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/readings/history")
    def get_history():
        frm = request.args.get("from")
        to = request.args.get("to")
        if frm and parse_iso_timestamp(frm) is None:
            return jsonify({"error": "from must be a valid ISO datetime."}), 400
        if to and parse_iso_timestamp(to) is None:
            return jsonify({"error": "to must be a valid ISO datetime."}), 400
        sql = "SELECT * FROM readings"
        params = []
        clauses = []
        if frm:
            clauses.append("timestamp >= ?")
            params.append(frm)
        if to:
            clauses.append("timestamp <= ?")
            params.append(to)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp ASC"
        rows = get_db().execute(sql, tuple(params)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/alerts")
    def get_alerts():
        rows = get_db().execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/summary/today")
    def summary_today():
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from_iso = day_start.isoformat()
        db = get_db()
        summary = db.execute(
            """
            SELECT ROUND(AVG(lux), 2) AS avg_lux, MAX(lux) AS max_lux, MIN(lux) AS min_lux
            FROM readings
            WHERE timestamp >= ?
            """,
            (from_iso,),
        ).fetchone()
        alert_row = db.execute(
            "SELECT COUNT(*) AS alert_count FROM alerts WHERE timestamp >= ?",
            (from_iso,),
        ).fetchone()
        return jsonify(
            {
                "avg_lux": summary["avg_lux"],
                "max_lux": summary["max_lux"],
                "min_lux": summary["min_lux"],
                "alert_count": alert_row["alert_count"],
            }
        )

    @app.get("/api/weather")
    def get_weather():
        latitude = request.args.get("latitude", type=float)
        longitude = request.args.get("longitude", type=float)
        if (latitude is None) != (longitude is None):
            return jsonify({"error": "latitude and longitude must be provided together."}), 400

        location = (
            request.args.get("location")
            or current_app.config.get("DEFAULT_WEATHER_LOCATION")
            or "Perth, Australia"
        ).strip()
        try:
            return jsonify(
                fetch_weather_summary(
                    location,
                    timeout=current_app.config.get("WEATHER_API_TIMEOUT_SECONDS", 4),
                    latitude=latitude,
                    longitude=longitude,
                )
            )
        except ValueError as err:
            return jsonify({"error": str(err)}), 404

    @app.get("/api/device-status")
    def device_status():
        state = get_db().execute("SELECT * FROM system_state WHERE id = 1").fetchone()
        last_seen = state["last_seen"]
        online = "offline"
        if last_seen:
            seen_time = datetime.fromisoformat(last_seen)
            if datetime.now(timezone.utc) - seen_time <= timedelta(seconds=30):
                online = "online"
        return jsonify(
            {
                "device_id": state["device_id"],
                "last_seen": last_seen,
                "online": online,
                "latest_wifi_signal": state["latest_wifi_signal"],
                "mode": state["mode"],
            }
        )

    @app.post("/api/demo/start")
    def demo_start():
        db = get_db()
        db.execute("UPDATE system_state SET mode = 'demo' WHERE id = 1")
        db.commit()
        current_app.extensions["demo_engine"].start()
        return jsonify({"success": True, "demo": True})

    @app.post("/api/demo/stop")
    def demo_stop():
        db = get_db()
        db.execute("UPDATE system_state SET mode = 'hardware' WHERE id = 1")
        db.commit()
        current_app.extensions["demo_engine"].stop()
        return jsonify({"success": True, "demo": False})

    @app.get("/api/demo/status")
    def demo_status():
        state = get_db().execute("SELECT mode FROM system_state WHERE id = 1").fetchone()
        return jsonify(
            {
                "mode": state["mode"] if state else "hardware",
                "active": current_app.extensions["demo_engine"].is_running(),
            }
        )

    @app.get("/api/system/status")
    def system_status():
        """Get system status for VEML6030 light sensor."""
        db = get_db()

        # Get latest reading
        latest = db.execute(
            "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()

        # Get current mode
        state = db.execute(
            "SELECT device_id, latest_wifi_signal, mode FROM system_state WHERE id = 1"
        ).fetchone()
        current_mode = state["mode"] if state else "hardware"

        # Check demo engine status
        demo_running = current_app.extensions["demo_engine"].is_running()

        return jsonify(
            {
                "sensor_info": {
                    "sensor": "VEML6030",
                    "sensor_type": "Ambient Light Sensor",
                    "measurement": "Illuminance (lux)",
                    "range": "0-188000 lux",
                },
                "system_info": {
                    "current_mode": current_mode,
                    "demo_engine_active": demo_running,
                    "device_id": state["device_id"] if state else "light-sensor-01",
                },
                "latest_reading": dict(latest) if latest else None,
                "light_levels": {
                    "too_dark": f"< {LOW_LIGHT_THRESHOLD_LUX} lux",
                    "dim": "50-500 lux",
                    "ideal": "500-5000 lux",
                    "bright": f"5000-{HIGH_LIGHT_THRESHOLD_LUX} lux",
                    "very_bright": f">= {HIGH_LIGHT_THRESHOLD_LUX} lux",
                },
                "thresholds": {
                    "low_lux": LOW_LIGHT_THRESHOLD_LUX,
                    "high_lux": HIGH_LIGHT_THRESHOLD_LUX,
                    "buzzer_on_when": ["Below Threshold", "Above Threshold"],
                },
            }
        )
