import json
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


DEFAULT_LOCATION = {
    "name": "Perth",
    "admin1": "Western Australia",
    "country": "Australia",
    "latitude": -31.9523,
    "longitude": 115.8613,
    "timezone": "Australia/Perth",
}

WEATHER_CODE_LABELS = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Dense Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    80: "Rain Showers",
    81: "Heavy Showers",
    82: "Violent Showers",
    95: "Thunderstorm",
    96: "Thunderstorm With Hail",
    99: "Severe Thunderstorm",
}


def _get_json(url, timeout):
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_url(base_url, params):
    return f"{base_url}?{urlencode(params)}"


def _condition_label(code):
    return WEATHER_CODE_LABELS.get(code, "Mixed Conditions")


def _location_label(location):
    parts = [location.get("name"), location.get("admin1"), location.get("country")]
    return ", ".join(part for part in parts if part)


def _safe_number(value, default=0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _geocode_location(location_name, timeout):
    if not location_name:
        return DEFAULT_LOCATION.copy()

    url = _build_url(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": location_name, "count": 1, "language": "en", "format": "json"},
    )
    data = _get_json(url, timeout)
    results = data.get("results") or []
    if not results:
        raise ValueError(f"No weather location found for '{location_name}'.")

    result = results[0]
    return {
        "name": result.get("name", location_name),
        "admin1": result.get("admin1", ""),
        "country": result.get("country", ""),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "timezone": result.get("timezone", "auto"),
    }


def _location_from_coordinates(location_name, latitude, longitude):
    return {
        "name": location_name or "Current hardware location",
        "admin1": "",
        "country": "",
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
    }


def _hourly_slice(weather_data):
    hourly = weather_data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return []

    current_time = (weather_data.get("current") or {}).get("time")
    start_index = 0
    if current_time:
        start_index = next((idx for idx, value in enumerate(times) if value >= current_time), 0)

    rows = []
    for idx in range(start_index, min(start_index + 12, len(times))):
        code = hourly.get("weather_code", [None] * len(times))[idx]
        rows.append(
            {
                "time": times[idx],
                "temperature_c": hourly.get("temperature_2m", [None] * len(times))[idx],
                "humidity_percent": hourly.get("relative_humidity_2m", [None] * len(times))[idx],
                "precipitation_probability_percent": hourly.get(
                    "precipitation_probability", [None] * len(times)
                )[idx],
                "precipitation_mm": hourly.get("precipitation", [None] * len(times))[idx],
                "cloud_cover_percent": hourly.get("cloud_cover", [None] * len(times))[idx],
                "wind_speed_kmh": hourly.get("wind_speed_10m", [None] * len(times))[idx],
                "uv_index": hourly.get("uv_index", [None] * len(times))[idx],
                "shortwave_radiation_w_m2": hourly.get(
                    "shortwave_radiation", [None] * len(times)
                )[idx],
                "weather_code": code,
                "condition": _condition_label(code),
            }
        )
    return rows


def _fallback_weather(location_name, reason):
    location = DEFAULT_LOCATION.copy()
    if location_name:
        location["name"] = location_name

    start = datetime.now().replace(minute=0, second=0, microsecond=0)
    hourly = []
    temperatures = [18, 19, 20, 22, 23, 24, 24, 23, 22, 20, 19, 18]
    humidity = [65, 63, 58, 52, 48, 45, 44, 48, 53, 58, 61, 64]
    clouds = [54, 48, 42, 34, 30, 28, 35, 44, 52, 58, 62, 68]
    for idx in range(12):
        code = 2 if clouds[idx] < 60 else 3
        hourly.append(
            {
                "time": (start + timedelta(hours=idx)).isoformat(timespec="minutes"),
                "temperature_c": temperatures[idx],
                "humidity_percent": humidity[idx],
                "precipitation_probability_percent": 18 + (idx % 4) * 7,
                "precipitation_mm": 0.1 if idx in (5, 6, 7) else 0,
                "cloud_cover_percent": clouds[idx],
                "wind_speed_kmh": 10 + idx % 5,
                "uv_index": max(0, 7 - abs(5 - idx)),
                "shortwave_radiation_w_m2": max(0, 720 - clouds[idx] * 7),
                "weather_code": code,
                "condition": _condition_label(code),
            }
        )

    return {
        "source": "fallback",
        "status": "degraded",
        "message": reason,
        "location": {**location, "label": _location_label(location)},
        "current": {
            "temperature_c": 23,
            "apparent_temperature_c": 22,
            "humidity_percent": 48,
            "precipitation_mm": 0.1,
            "cloud_cover_percent": 35,
            "wind_speed_kmh": 13,
            "wind_direction_degrees": 248,
            "wind_gust_kmh": 24,
            "weather_code": 2,
            "condition": _condition_label(2),
            "is_day": 1,
            "uv_index": 6.8,
            "shortwave_radiation_w_m2": 475,
            "aqi": 42,
            "pm2_5": 7.6,
        },
        "daily": {
            "precipitation_sum_mm": 0.8,
            "uv_index_max": 7.1,
            "sunrise": None,
            "sunset": None,
        },
        "hourly": hourly,
    }


def fetch_weather_summary(location_name=None, timeout=4, latitude=None, longitude=None):
    try:
        if latitude is not None and longitude is not None:
            location = _location_from_coordinates(location_name, latitude, longitude)
        else:
            location = _geocode_location(location_name, timeout)
        latitude = location["latitude"]
        longitude = location["longitude"]
        timezone = location.get("timezone") or "auto"

        weather_url = _build_url(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "is_day",
                        "precipitation",
                        "rain",
                        "weather_code",
                        "cloud_cover",
                        "wind_speed_10m",
                        "wind_direction_10m",
                        "wind_gusts_10m",
                        "shortwave_radiation",
                    ]
                ),
                "hourly": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "precipitation_probability",
                        "precipitation",
                        "cloud_cover",
                        "weather_code",
                        "wind_speed_10m",
                        "uv_index",
                        "shortwave_radiation",
                    ]
                ),
                "daily": "uv_index_max,precipitation_sum,sunrise,sunset",
                "forecast_days": 2,
                "timezone": timezone,
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "temperature_unit": "celsius",
            },
        )
        weather_data = _get_json(weather_url, timeout)

        air_url = _build_url(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": "us_aqi,pm2_5,uv_index",
                "hourly": "us_aqi,pm2_5,uv_index",
                "forecast_hours": 12,
                "timezone": timezone,
            },
        )
        air_data = _get_json(air_url, timeout)
        current = weather_data.get("current") or {}
        daily = weather_data.get("daily") or {}
        air_current = air_data.get("current") or {}
        hourly = weather_data.get("hourly") or {}
        weather_code = current.get("weather_code")
        current_shortwave = current.get("shortwave_radiation")
        if current_shortwave is None:
            hourly_shortwave = hourly.get("shortwave_radiation") or []
            current_shortwave = hourly_shortwave[0] if hourly_shortwave else None

        return {
            "source": "open-meteo",
            "status": "ok",
            "message": "",
            "location": {**location, "label": _location_label(location)},
            "current": {
                "temperature_c": current.get("temperature_2m"),
                "apparent_temperature_c": current.get("apparent_temperature"),
                "humidity_percent": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "cloud_cover_percent": current.get("cloud_cover"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "wind_direction_degrees": current.get("wind_direction_10m"),
                "wind_gust_kmh": current.get("wind_gusts_10m"),
                "weather_code": weather_code,
                "condition": _condition_label(weather_code),
                "is_day": current.get("is_day"),
                "uv_index": air_current.get("uv_index")
                or (daily.get("uv_index_max") or [None])[0],
                "shortwave_radiation_w_m2": current_shortwave,
                "aqi": air_current.get("us_aqi"),
                "pm2_5": air_current.get("pm2_5"),
            },
            "daily": {
                "precipitation_sum_mm": (daily.get("precipitation_sum") or [None])[0],
                "uv_index_max": (daily.get("uv_index_max") or [None])[0],
                "sunrise": (daily.get("sunrise") or [None])[0],
                "sunset": (daily.get("sunset") or [None])[0],
            },
            "hourly": _hourly_slice(weather_data),
        }
    except ValueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as err:
        return _fallback_weather(location_name, f"Weather API unavailable: {err}")
