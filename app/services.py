from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_risk_level(uv_index):
    uv = float(uv_index)
    if 0 <= uv < 3:
        return "Low"
    if 3 <= uv < 6:
        return "Moderate"
    return "High"


def get_alert_message(risk_level):
    if risk_level == "Moderate":
        return "Moderate UV. Wear protection."
    if risk_level == "High":
        return "High UV. Take precautions immediately."
    return "Low UV."


def parse_iso_timestamp(value):
    if not value:
        return None
    try:
        # Accept `Z` suffix and normalize to UTC ISO output.
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def persist_reading(db, payload):
    uv_index = float(payload["uv_index"])
    risk = get_risk_level(uv_index)
    timestamp = payload.get("timestamp") or now_iso()
    wifi_signal = payload.get("wifi_signal")
    wifi_signal = int(wifi_signal) if wifi_signal is not None else None
    source = payload.get("source", "hardware")

    db.execute(
        """
        INSERT INTO readings (timestamp, device_id, uv_index, risk_level, wifi_signal, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (timestamp, payload["device_id"], uv_index, risk, wifi_signal, source),
    )

    db.execute(
        """
        UPDATE system_state
        SET device_id = ?, last_seen = ?, latest_wifi_signal = ?
        WHERE id = 1
        """,
        (payload["device_id"], timestamp, wifi_signal),
    )

    if risk in ("Moderate", "High"):
        db.execute(
            """
            INSERT INTO alerts (timestamp, device_id, uv_index, risk_level, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (timestamp, payload["device_id"], uv_index, risk, get_alert_message(risk)),
        )

    db.commit()
    return {
        "timestamp": timestamp,
        "device_id": payload["device_id"],
        "uv_index": uv_index,
        "risk_level": risk,
        "wifi_signal": wifi_signal,
        "source": source,
    }
