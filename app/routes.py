import csv
import io
from datetime import datetime, timedelta, timezone

from flask import Response, current_app, jsonify, render_template, request

from .db import get_db
from .services import (
    ACCEPTABLE_LIGHT_MAX_LUX,
    BRIGHT_LIGHT_MAX_LUX,
    MAX_VEML6030_LUX,
    POOR_VISIBILITY_MAX_LUX,
    VERY_DARK_MAX_LUX,
    build_environmental_comparison,
    legacy_light_level,
    legacy_threshold_status,
    now_iso,
    parse_iso_timestamp,
    persist_reading,
    update_device_status,
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
    if lux < 0 or lux > MAX_VEML6030_LUX:
        return f"lux must be between 0 and {MAX_VEML6030_LUX}."

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

    timestamp = payload.get("timestamp")
    if timestamp is not None and parse_iso_timestamp(timestamp) is None:
        return "timestamp must be a valid ISO datetime when provided."

    source = payload.get("source", "hardware")
    if source not in ("hardware", "simulation", "csv", "legacy"):
        return "source must be hardware, simulation, csv, or legacy."

    return None


def _latest_reading(db):
    row = db.execute(
        "SELECT * FROM light_readings ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    return _serialize_reading(dict(row)) if row else None


def _recent_readings(db, limit=60):
    rows = db.execute(
        """
        SELECT *
        FROM light_readings
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_serialize_reading(dict(row)) for row in rows]


def _serialize_reading(reading):
    if not reading:
        return reading
    lux = reading.get("lux", 0)
    reading.setdefault("light_level", legacy_light_level(lux))
    reading.setdefault("threshold_status", legacy_threshold_status(lux))
    reading.setdefault("buzzer_state", reading.get("buzzer"))
    return reading


def _serialize_alert(alert):
    payload = dict(alert)
    payload.setdefault("light_level", legacy_light_level(payload.get("lux", 0)))
    return payload


def _device_status_payload(db):
    state = db.execute("SELECT * FROM device_status WHERE id = 1").fetchone()
    if not state:
        return None
    last_seen = state["last_seen"]
    online = "offline"
    if last_seen:
        seen_time = datetime.fromisoformat(last_seen)
        if datetime.now(timezone.utc) - seen_time <= timedelta(seconds=30):
            online = "online"
    payload = dict(state)
    payload["online"] = online
    payload["signal_active"] = bool(payload["signal_active"])
    return payload


def register_routes(app):
    @app.get("/")
    def dashboard_page():
        return render_template("index.html")

    @app.get("/live-data")
    def live_data_page():
        return render_template("live-data.html")

    @app.get("/history")
    def history_page():
        return render_template("history.html")

    @app.get("/weather-comparison")
    def weather_comparison_page():
        return render_template("weather-comparison.html")

    @app.get("/alerts")
    def alerts_page():
        return render_template("alerts.html")

    @app.get("/devices")
    def devices_page():
        return render_template("devices.html")

    @app.get("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.get("/how-it-works")
    def how_it_works_page():
        return render_template("how-it-works.html")

    @app.get("/about")
    def about_page():
        return render_template("about.html")

    @app.get("/api/health")
    def health():
        return jsonify({"backend": "ok", "database": "ok", "timestamp": now_iso()})

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

        payload["timestamp"] = parse_iso_timestamp(payload.get("timestamp")) or now_iso()
        reading = persist_reading(get_db(), payload)
        return jsonify({"success": True, "reading": reading}), 201

    @app.post("/api/device-status")
    def post_device_status():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Payload must be a JSON object."}), 400
        update_device_status(get_db(), payload)
        return jsonify({"success": True, "device_status": _device_status_payload(get_db())}), 200

    @app.get("/api/readings/latest")
    def get_latest():
        return jsonify(_latest_reading(get_db()))

    @app.get("/api/readings/recent")
    def get_recent():
        limit = request.args.get("limit", default=20, type=int)
        if limit < 1 or limit > 500:
            return jsonify({"error": "limit must be between 1 and 500."}), 400
        return jsonify(_recent_readings(get_db(), limit=limit))

    @app.get("/api/history")
    def get_history():
        frm = request.args.get("from")
        to = request.args.get("to")
        if frm and parse_iso_timestamp(frm) is None:
            return jsonify({"error": "from must be a valid ISO datetime."}), 400
        if to and parse_iso_timestamp(to) is None:
            return jsonify({"error": "to must be a valid ISO datetime."}), 400

        sql = "SELECT * FROM light_readings"
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
        return jsonify([_serialize_reading(dict(row)) for row in rows])

    @app.get("/api/alerts")
    def get_alerts():
        rows = get_db().execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 120"
        ).fetchall()
        return jsonify([_serialize_alert(row) for row in rows])

    @app.get("/api/summary/today")
    def summary_today():
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from_iso = day_start.isoformat()
        db = get_db()
        summary = db.execute(
            """
            SELECT
                ROUND(AVG(lux), 2) AS avg_lux,
                MAX(lux) AS max_lux,
                MIN(lux) AS min_lux,
                SUM(CASE WHEN lux <= ? THEN 1 ELSE 0 END) AS low_light_samples
            FROM light_readings
            WHERE timestamp >= ?
            """,
            (POOR_VISIBILITY_MAX_LUX, from_iso),
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
                "low_light_samples": summary["low_light_samples"] or 0,
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
                    api_key=current_app.config.get("WEATHER_API_KEY", ""),
                )
            )
        except ValueError as err:
            return jsonify({"error": str(err)}), 404

    @app.get("/api/environmental-comparison")
    def get_environmental_comparison():
        db = get_db()
        latest = _latest_reading(db)
        recent = _recent_readings(db, limit=12)
        latitude = request.args.get("latitude", type=float)
        longitude = request.args.get("longitude", type=float)
        location = (
            request.args.get("location")
            or (latest or {}).get("location_label")
            or current_app.config.get("DEFAULT_WEATHER_LOCATION")
        )
        weather = fetch_weather_summary(
            location,
            timeout=current_app.config.get("WEATHER_API_TIMEOUT_SECONDS", 4),
            latitude=latitude,
            longitude=longitude,
            api_key=current_app.config.get("WEATHER_API_KEY", ""),
        )
        return jsonify(build_environmental_comparison(latest, weather, recent))

    @app.get("/api/device-status")
    def device_status():
        return jsonify(_device_status_payload(get_db()))

    @app.get("/api/export/readings.csv")
    def export_readings_csv():
        rows = get_db().execute(
            """
            SELECT timestamp, device_id, lux, status, buzzer, source
            FROM light_readings
            ORDER BY timestamp DESC
            """
        ).fetchall()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "device_id", "lux", "status", "buzzer", "source"])
        for row in rows:
            writer.writerow(
                [
                    row["timestamp"],
                    row["device_id"],
                    row["lux"],
                    row["status"],
                    row["buzzer"],
                    row["source"],
                ]
            )
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=ambient-light-readings.csv"},
        )

    @app.post("/api/simulation/csv")
    def simulation_csv():
        uploaded = request.files.get("file")
        if uploaded is None:
            return jsonify({"error": "Upload a CSV file using field name 'file'."}), 400
        text = uploaded.read().decode("utf-8-sig")
        label = uploaded.filename or "Uploaded CSV simulation"
        try:
            current_app.extensions["demo_engine"].load_csv_text(text, label=label)
        except ValueError as err:
            return jsonify({"error": str(err)}), 400
        db = get_db()
        db.execute(
            "UPDATE system_state SET simulation_label = ?, mode = 'demo' WHERE id = 1",
            (label,),
        )
        db.commit()
        return jsonify({"success": True, "label": label})

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

    @app.post("/api/demo/reset")
    def demo_reset():
        current_app.extensions["demo_engine"].reset_default_rows()
        db = get_db()
        db.execute(
            "UPDATE system_state SET simulation_label = 'Built-in light cycle' WHERE id = 1"
        )
        db.commit()
        return jsonify({"success": True})

    @app.get("/api/demo/status")
    def demo_status():
        state = get_db().execute(
            "SELECT mode, simulation_label FROM system_state WHERE id = 1"
        ).fetchone()
        return jsonify(
            {
                "mode": state["mode"] if state else "hardware",
                "active": current_app.extensions["demo_engine"].is_running(),
                "label": state["simulation_label"] if state else "Built-in light cycle",
            }
        )

    @app.get("/api/system/status")
    def system_status():
        return jsonify(
            {
                "sensor_info": {
                    "sensor": "VEML6030",
                    "sensor_type": "Ambient Visible Light Sensor",
                    "measurement": "Illuminance (lux)",
                    "range": f"0-{MAX_VEML6030_LUX} lux",
                },
                "thresholds": {
                    "very_dark": f"0-{VERY_DARK_MAX_LUX} lux",
                    "poor_visibility": f"{VERY_DARK_MAX_LUX + 1}-{POOR_VISIBILITY_MAX_LUX} lux",
                    "acceptable": f"{POOR_VISIBILITY_MAX_LUX + 1}-{ACCEPTABLE_LIGHT_MAX_LUX} lux",
                    "bright": f"{ACCEPTABLE_LIGHT_MAX_LUX + 1}-{BRIGHT_LIGHT_MAX_LUX} lux",
                    "night_excessive": f"{BRIGHT_LIGHT_MAX_LUX}+ lux",
                },
                "device_status": _device_status_payload(get_db()),
            }
        )
