from datetime import datetime, timezone

LOW_LIGHT_THRESHOLD_LUX = 50
HIGH_LIGHT_THRESHOLD_LUX = 50000


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_light_level(lux):
    """Classify light levels from VEML6030 sensor (lux readings)."""
    lux = float(lux)
    if lux < LOW_LIGHT_THRESHOLD_LUX:
        return "Too Dark"
    if lux < 500:
        return "Dim"
    if lux < 5000:
        return "Ideal"
    if lux < HIGH_LIGHT_THRESHOLD_LUX:
        return "Bright"
    return "Very Bright"


def get_threshold_status(lux):
    lux = float(lux)
    if lux < LOW_LIGHT_THRESHOLD_LUX:
        return "Below Threshold"
    if lux >= HIGH_LIGHT_THRESHOLD_LUX:
        return "Above Threshold"
    return "Within Threshold"


def get_buzzer_state(threshold_status):
    return "ON" if threshold_status != "Within Threshold" else "OFF"


def get_oled_message(lux, light_level, buzzer_state):
    return f"Lux {round(float(lux), 1)} | {light_level} | Buzzer {buzzer_state}"


def get_alert_message(light_level):
    """Generate alert messages for extreme light conditions."""
    if light_level == "Too Dark":
        return "Light too low. Increase illumination for better visibility."
    if light_level == "Very Bright":
        return "Light very bright. May cause eye strain or glare."
    return "Light level normal."


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
    """Store light sensor reading in database."""
    lux = float(payload["lux"])
    light_level = get_light_level(lux)
    threshold_status = get_threshold_status(lux)
    buzzer_state = get_buzzer_state(threshold_status)
    oled_message = get_oled_message(lux, light_level, buzzer_state)
    timestamp = payload.get("timestamp") or now_iso()
    wifi_signal = payload.get("wifi_signal")
    wifi_signal = int(wifi_signal) if wifi_signal is not None else None
    source = payload.get("source", "hardware")
    location_label = payload.get("location_label")
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    latitude = float(latitude) if latitude not in (None, "") else None
    longitude = float(longitude) if longitude not in (None, "") else None

    db.execute(
        """
        INSERT INTO readings (
            timestamp,
            device_id,
            lux,
            light_level,
            threshold_status,
            buzzer_state,
            oled_message,
            wifi_signal,
            source,
            location_label,
            latitude,
            longitude
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            payload["device_id"],
            lux,
            light_level,
            threshold_status,
            buzzer_state,
            oled_message,
            wifi_signal,
            source,
            location_label,
            latitude,
            longitude,
        ),
    )

    db.execute(
        """
        UPDATE system_state
        SET device_id = ?, last_seen = ?, latest_wifi_signal = ?
        WHERE id = 1
        """,
        (payload["device_id"], timestamp, wifi_signal),
    )

    # Create alerts for extreme conditions
    if light_level in ("Too Dark", "Very Bright"):
        db.execute(
            """
            INSERT INTO alerts (timestamp, device_id, lux, light_level, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                payload["device_id"],
                lux,
                light_level,
                get_alert_message(light_level),
            ),
        )

    db.commit()
    return {
        "timestamp": timestamp,
        "device_id": payload["device_id"],
        "lux": lux,
        "light_level": light_level,
        "threshold_status": threshold_status,
        "buzzer_state": buzzer_state,
        "oled_message": oled_message,
        "wifi_signal": wifi_signal,
        "source": source,
        "location_label": location_label,
        "latitude": latitude,
        "longitude": longitude,
    }
