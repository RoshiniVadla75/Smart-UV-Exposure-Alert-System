from datetime import datetime, timedelta, timezone

from flask import current_app, jsonify, render_template, request

from .db import get_db
from .services import now_iso, parse_iso_timestamp, persist_reading


def _validate_payload(payload):
    if not isinstance(payload, dict):
        return "Payload must be a JSON object."
    if not payload.get("device_id") or not isinstance(payload.get("device_id"), str):
        return "device_id is required and must be a string."
    uv = payload.get("uv_index")
    try:
        uv = float(uv)
    except (TypeError, ValueError):
        return "uv_index is required and must be a number."
    if uv < 0 or uv > 15:
        return "uv_index must be between 0 and 15."
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
        return render_template("live-data.html")

    @app.get("/history")
    def history_page():
        return render_template("history.html")

    @app.get("/alerts")
    def alerts_page():
        return render_template("alerts.html")

    @app.get("/devices")
    def devices_page():
        return render_template("devices.html")

    @app.get("/how-it-works")
    def how_it_works_page():
        return render_template("how-it-works.html")

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
            SELECT ROUND(AVG(uv_index), 2) AS avg_uv, MAX(uv_index) AS max_uv
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
                "avg_uv": summary["avg_uv"],
                "max_uv": summary["max_uv"],
                "alert_count": alert_row["alert_count"],
            }
        )

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
