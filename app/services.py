from datetime import datetime, timezone


VERY_DARK_MAX_LUX = 10
POOR_VISIBILITY_MAX_LUX = 30
ACCEPTABLE_LIGHT_MAX_LUX = 100
BRIGHT_LIGHT_MAX_LUX = 500
MAX_VEML6030_LUX = 188000

FOG_CODES = {45, 48}
RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_iso_timestamp(value):
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def classify_lighting(lux):
    value = float(lux)
    if value <= VERY_DARK_MAX_LUX:
        return {
            "status": "Very Dark",
            "led_color": "red",
            "buzzer": "ON",
            "alert_type": "darkness",
            "summary": "Dangerous darkness detected.",
        }
    if value <= POOR_VISIBILITY_MAX_LUX:
        return {
            "status": "Poor Visibility",
            "led_color": "yellow",
            "buzzer": "BEEP",
            "alert_type": "visibility_warning",
            "summary": "Visibility is reduced.",
        }
    if value <= ACCEPTABLE_LIGHT_MAX_LUX:
        return {
            "status": "Acceptable Street Lighting",
            "led_color": "green",
            "buzzer": "OFF",
            "alert_type": None,
            "summary": "Street-light brightness is acceptable.",
        }
    if value <= BRIGHT_LIGHT_MAX_LUX:
        return {
            "status": "Bright",
            "led_color": "green",
            "buzzer": "OFF",
            "alert_type": None,
            "summary": "The environment is brightly illuminated.",
        }
    return {
        "status": "High Ambient Brightness",
        "led_color": "green",
        "buzzer": "OFF",
        "alert_type": None,
        "summary": "High ambient brightness detected. Use daylight context to decide whether it is abnormal.",
    }


def legacy_light_level(lux):
    value = float(lux)
    if value < 50:
        return "Too Dark"
    if value < 500:
        return "Dim"
    if value < 5000:
        return "Ideal"
    if value < 50000:
        return "Bright"
    return "Very Bright"


def legacy_threshold_status(lux):
    value = float(lux)
    if value < 50:
        return "Below Threshold"
    if value >= 50000:
        return "Above Threshold"
    return "Within Threshold"


def get_oled_message(lux, status, buzzer, ble_status):
    return "\n".join(
        [
            f"Lux {round(float(lux), 1)}",
            f"Status: {status}",
            f"Buzzer: {buzzer}",
            f"BLE: {ble_status.title()}",
        ]
    )


def _recent_previous_reading(db, device_id):
    return db.execute(
        """
        SELECT lux
        FROM light_readings
        WHERE device_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()


def detect_sudden_drop(previous_lux, current_lux):
    if previous_lux is None:
        return False
    previous = float(previous_lux)
    current = float(current_lux)
    if previous < 20:
        return False
    absolute_drop = previous - current
    relative_drop = absolute_drop / previous if previous else 0
    return absolute_drop >= 20 and relative_drop >= 0.6


def _insert_alert(db, timestamp, device_id, lux, alert_type, message):
    db.execute(
        """
        INSERT INTO alerts (timestamp, device_id, lux, alert_type, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (timestamp, device_id, float(lux), alert_type, message),
    )


def _bool_to_int(value, default=0):
    if value is None:
        return default
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"1", "true", "yes", "active", "connected", "on"} else 0
    return 1 if bool(value) else 0


def _optional_float(value):
    return float(value) if value not in (None, "") else None


def _optional_int(value):
    return int(value) if value not in (None, "") else None


def persist_reading(db, payload):
    lux = float(payload["lux"])
    lighting = classify_lighting(lux)
    timestamp = payload.get("timestamp") or now_iso()
    device_id = payload["device_id"]
    ble_status = payload.get("ble_status") or "connected"
    signal_active = _bool_to_int(payload.get("signal_active"), default=1)
    location_label = payload.get("location_label")
    latitude = _optional_float(payload.get("latitude"))
    longitude = _optional_float(payload.get("longitude"))
    uptime_seconds = _optional_int(payload.get("esp32_uptime_seconds"))
    previous = _recent_previous_reading(db, device_id)
    sudden_drop = detect_sudden_drop(previous["lux"] if previous else None, lux)
    oled_message = get_oled_message(lux, lighting["status"], lighting["buzzer"], ble_status)
    source = payload.get("source", "hardware")
    last_packet = payload.get("raw_packet")

    db.execute(
        """
        INSERT INTO light_readings (
            timestamp,
            device_id,
            lux,
            status,
            buzzer,
            source,
            oled_message,
            led_color,
            sudden_drop,
            ble_status,
            signal_active,
            location_label,
            latitude,
            longitude
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            device_id,
            lux,
            lighting["status"],
            lighting["buzzer"],
            source,
            oled_message,
            lighting["led_color"],
            1 if sudden_drop else 0,
            ble_status,
            signal_active,
            location_label,
            latitude,
            longitude,
        ),
    )

    db.execute(
        """
        UPDATE device_status
        SET
            device_id = ?,
            last_seen = ?,
            ble_status = ?,
            signal_active = ?,
            sensor_status = ?,
            oled_status = ?,
            buzzer_status = ?,
            esp32_uptime_seconds = ?,
            last_packet = ?
        WHERE id = 1
        """,
        (
            device_id,
            timestamp,
            ble_status,
            signal_active,
            payload.get("sensor_status", "active"),
            payload.get("oled_status", "active"),
            lighting["buzzer"],
            uptime_seconds,
            last_packet,
        ),
    )

    if lighting["status"] == "Very Dark":
        _insert_alert(
            db,
            timestamp,
            device_id,
            lux,
            "darkness",
            "Very dark ambient light detected. Visibility and street-light coverage should be checked.",
        )
    if lighting["buzzer"] in {"ON", "BEEP"}:
        _insert_alert(
            db,
            timestamp,
            device_id,
            lux,
            "buzzer_activation",
            f"Buzzer state changed to {lighting['buzzer']} for {lighting['status'].lower()} conditions.",
        )

    if sudden_drop:
        _insert_alert(
            db,
            timestamp,
            device_id,
            lux,
            "sudden_light_drop",
            "Sudden brightness drop detected. Possible lamp failure, obstruction, or abrupt weather change.",
        )

    db.commit()
    return {
        "timestamp": timestamp,
        "device_id": device_id,
        "lux": lux,
        "status": lighting["status"],
        "light_level": legacy_light_level(lux),
        "buzzer": lighting["buzzer"],
        "buzzer_state": lighting["buzzer"],
        "threshold_status": legacy_threshold_status(lux),
        "source": source,
        "oled_message": oled_message,
        "led_color": lighting["led_color"],
        "sudden_drop": sudden_drop,
        "ble_status": ble_status,
        "signal_active": bool(signal_active),
        "location_label": location_label,
        "latitude": latitude,
        "longitude": longitude,
        "esp32_uptime_seconds": uptime_seconds,
    }


def update_device_status(db, payload):
    last_seen = payload.get("last_seen") or now_iso()
    db.execute(
        """
        UPDATE device_status
        SET
            device_id = COALESCE(?, device_id),
            last_seen = ?,
            ble_status = COALESCE(?, ble_status),
            signal_active = COALESCE(?, signal_active),
            sensor_status = COALESCE(?, sensor_status),
            oled_status = COALESCE(?, oled_status),
            buzzer_status = COALESCE(?, buzzer_status),
            esp32_uptime_seconds = COALESCE(?, esp32_uptime_seconds),
            last_packet = COALESCE(?, last_packet)
        WHERE id = 1
        """,
        (
            payload.get("device_id"),
            last_seen,
            payload.get("ble_status"),
            _bool_to_int(payload.get("signal_active")) if "signal_active" in payload else None,
            payload.get("sensor_status"),
            payload.get("oled_status"),
            payload.get("buzzer_status"),
            _optional_int(payload.get("esp32_uptime_seconds")),
            payload.get("last_packet"),
        ),
    )
    db.commit()


def _trend_label(recent_readings):
    rows = list(recent_readings or [])
    if len(rows) < 2:
        return "Trend building"
    oldest = float(rows[-1]["lux"])
    latest = float(rows[0]["lux"])
    delta = latest - oldest
    if abs(delta) < max(5, oldest * 0.12):
        return "Lighting levels stable"
    return "Brightness rising" if delta > 0 else "Brightness falling"


def build_environmental_comparison(reading, weather_summary, recent_readings=None):
    if not reading:
        return {
            "sensor_lux": None,
            "daylight_status": "Unknown",
            "weather_condition": "Waiting for sensor data",
            "expected": "Insufficient data",
            "analysis": "No local ambient-light reading is available yet.",
            "recommendation": "Connect the BLE device or start CSV simulation.",
            "trend": "Trend building",
            "category": "neutral",
        }

    current_weather = (weather_summary or {}).get("current") or {}
    weather_condition = current_weather.get("condition") or "Mixed Conditions"
    weather_code = current_weather.get("weather_code")
    cloud_cover = float(current_weather.get("cloud_cover_percent") or 0)
    precipitation = float(current_weather.get("precipitation_mm") or 0)
    is_day = int(current_weather.get("is_day") or 0) == 1
    daylight_status = "Daylight" if is_day else "Night"
    rainy = weather_code in RAIN_CODES or precipitation > 0
    foggy = weather_code in FOG_CODES or "fog" in weather_condition.lower()
    lux = float(reading["lux"])
    sudden_drop = bool(reading.get("sudden_drop"))

    if not is_day:
        expected = "Low ambient brightness expected"
        if lux > BRIGHT_LIGHT_MAX_LUX:
            analysis = "Excessive brightness detected during night conditions."
            recommendation = "Review nearby street-light output, glare, or unnecessary over-illumination."
            category = "critical"
        elif lux <= VERY_DARK_MAX_LUX:
            analysis = "Night conditions and very low local brightness align, but visibility remains poor."
            recommendation = "Check whether the monitored street-light zone needs stronger coverage."
            category = "warning"
        else:
            analysis = "Local brightness is consistent with night-time street-light monitoring conditions."
            recommendation = "Continue tracking trend stability and sudden drop alerts."
            category = "positive"
    elif foggy or rainy or cloud_cover >= 75:
        expected = "Reduced environmental brightness expected"
        if lux <= VERY_DARK_MAX_LUX:
            analysis = "Unexpected low brightness detected during active daylight conditions."
            recommendation = "Inspect shading, obstruction, sensor placement, or a local lighting fault."
            category = "critical"
        else:
            analysis = "Brightness levels are consistent with cloudy, rainy, or foggy daylight conditions."
            recommendation = "Use the trend graph to watch whether local visibility keeps declining."
            category = "positive"
    elif cloud_cover >= 40:
        expected = "Variable daylight brightness expected"
        if lux <= POOR_VISIBILITY_MAX_LUX:
            analysis = "Local brightness is lower than expected for the present daylight conditions."
            recommendation = "Check obstruction, deep shade, or possible street-light coverage issues."
            category = "warning"
        else:
            analysis = "Brightness trends broadly match partly cloudy daylight conditions."
            recommendation = "No immediate intervention is needed unless a sharp drop appears."
            category = "positive"
    else:
        expected = "Bright environment expected"
        if lux <= POOR_VISIBILITY_MAX_LUX:
            analysis = "Unexpected low brightness detected."
            recommendation = "Possible obstruction, shading, weather anomaly, or lighting issue."
            category = "critical"
        else:
            analysis = "Brightness levels are consistent with clear daytime environmental conditions."
            recommendation = "Use alerts to catch sudden local drops rather than treating this as abnormal."
            category = "positive"

    if sudden_drop:
        analysis = f"{analysis} Sudden brightness drop detected."
        recommendation = "Inspect the monitored zone for lamp failure, sensor blockage, or abrupt visibility loss."
        category = "critical"

    return {
        "sensor_lux": lux,
        "daylight_status": daylight_status,
        "weather_condition": weather_condition,
        "cloud_cover_percent": cloud_cover,
        "precipitation_mm": precipitation,
        "expected": expected,
        "analysis": analysis,
        "recommendation": recommendation,
        "trend": _trend_label(recent_readings),
        "category": category,
    }
