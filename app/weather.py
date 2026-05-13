import json
import os
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
    if code is None:
        return "Weather unavailable"
    return WEATHER_CODE_LABELS.get(code, "Mixed Conditions")


def _location_label(location):
    parts = [location.get("name"), location.get("admin1"), location.get("country")]
    return ", ".join(part for part in parts if part)


def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(values):
    return values[0] if values else None


def _normalize_location_name(location_name):
    return (location_name or "Perth, Western Australia").strip()


def _geocode_location(location_name, timeout):
    normalized = _normalize_location_name(location_name)
    if normalized.lower() in {"perth", "perth, australia", "perth, western australia"}:
        return DEFAULT_LOCATION.copy()

    url = _build_url(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": normalized, "count": 1, "language": "en", "format": "json"},
    )
    data = _get_json(url, timeout)
    results = data.get("results") or []
    if not results:
        raise ValueError(f"No weather location found for '{normalized}'.")

    result = results[0]
    return {
        "name": result.get("name", normalized),
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


def _value_at(values, index):
    if not values or index < 0 or index >= len(values):
        return None
    return values[index]


def _nearest_hour_index(times, current_time):
    if not times:
        return 0
    if not current_time:
        return 0
    return next((idx for idx, value in enumerate(times) if value >= current_time), 0)


def _hourly_slice(weather_data):
    hourly = weather_data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return []

    current_time = (weather_data.get("current") or {}).get("time")
    start_index = _nearest_hour_index(times, current_time)
    rows = []
    for idx in range(start_index, min(start_index + 12, len(times))):
        code = _value_at(hourly.get("weather_code"), idx)
        rows.append(
            {
                "time": times[idx],
                "temperature_c": _value_at(hourly.get("temperature_2m"), idx),
                "humidity_percent": _value_at(hourly.get("relative_humidity_2m"), idx),
                "wind_speed_kmh": _value_at(hourly.get("wind_speed_10m"), idx),
                "cloud_cover_percent": _value_at(hourly.get("cloud_cover"), idx),
                "uv_index": _value_at(hourly.get("uv_index"), idx),
                "precipitation_probability_percent": _value_at(
                    hourly.get("precipitation_probability"), idx
                ),
                "precipitation_mm": _value_at(hourly.get("precipitation"), idx),
                "weather_code": code,
                "condition": _condition_label(code),
                "is_day": _value_at(hourly.get("is_day"), idx),
            }
        )
    return rows


def _forecast_from_open_meteo(weather_data):
    daily = weather_data.get("daily") or {}
    dates = daily.get("time") or []
    forecast = []
    for idx, date_value in enumerate(dates):
        code = _value_at(daily.get("weather_code"), idx)
        forecast.append(
            {
                "date": date_value,
                "condition": _condition_label(code),
                "weather_code": code,
                "temperature_max_c": _value_at(daily.get("temperature_2m_max"), idx),
                "temperature_min_c": _value_at(daily.get("temperature_2m_min"), idx),
                "uv_index_max": _value_at(daily.get("uv_index_max"), idx),
                "precipitation_sum_mm": _value_at(daily.get("precipitation_sum"), idx),
                "sunrise": _value_at(daily.get("sunrise"), idx),
                "sunset": _value_at(daily.get("sunset"), idx),
            }
        )
    return forecast


def _current_hour_values(weather_data):
    hourly = weather_data.get("hourly") or {}
    times = hourly.get("time") or []
    idx = _nearest_hour_index(times, (weather_data.get("current") or {}).get("time"))
    return {
        "uv_index": _value_at(hourly.get("uv_index"), idx),
        "humidity_percent": _value_at(hourly.get("relative_humidity_2m"), idx),
        "wind_speed_kmh": _value_at(hourly.get("wind_speed_10m"), idx),
    }


def _unavailable_weather(location_name, reason):
    location = DEFAULT_LOCATION.copy()
    if location_name:
        location["name"] = location_name
    return {
        "source": "unavailable",
        "source_label": "Weather unavailable",
        "status": "error",
        "note": reason,
        "location": {**location, "label": _location_label(location)},
        "current": {
            "temperature_c": None,
            "humidity_percent": None,
            "wind_speed_kmh": None,
            "cloud_cover_percent": None,
            "uv_index": None,
            "precipitation_mm": None,
            "rain_mm": None,
            "weather_code": None,
            "condition": "Weather unavailable",
            "is_day": None,
        },
        "daily": {
            "uv_index_max": None,
            "precipitation_sum_mm": None,
            "sunrise": None,
            "sunset": None,
        },
        "hourly": [],
        "forecast": [],
    }


def _fetch_open_meteo(location_name, timeout, latitude=None, longitude=None):
    if latitude is not None and longitude is not None:
        location = _location_from_coordinates(location_name, latitude, longitude)
    else:
        location = _geocode_location(location_name, timeout)

    weather_url = _build_url(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "is_day",
                    "precipitation",
                    "rain",
                    "weather_code",
                    "cloud_cover",
                    "wind_speed_10m",
                ]
            ),
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "cloud_cover",
                    "weather_code",
                    "is_day",
                    "precipitation_probability",
                    "precipitation",
                    "uv_index",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "uv_index_max",
                    "precipitation_sum",
                    "sunrise",
                    "sunset",
                ]
            ),
            "forecast_days": 7,
            "timezone": location.get("timezone") or "auto",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        },
    )
    weather_data = _get_json(weather_url, timeout)
    current = weather_data.get("current") or {}
    daily = weather_data.get("daily") or {}
    hour_values = _current_hour_values(weather_data)
    weather_code = current.get("weather_code")

    return {
        "source": "open-meteo",
        "source_label": "Live weather",
        "status": "ok",
        "note": "Live weather from Open-Meteo",
        "location": {**location, "label": _location_label(location)},
        "current": {
            "time": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m")
            or hour_values.get("humidity_percent"),
            "wind_speed_kmh": current.get("wind_speed_10m") or hour_values.get("wind_speed_kmh"),
            "cloud_cover_percent": current.get("cloud_cover"),
            "uv_index": hour_values.get("uv_index"),
            "precipitation_mm": current.get("precipitation"),
            "rain_mm": current.get("rain"),
            "weather_code": weather_code,
            "condition": _condition_label(weather_code),
            "is_day": current.get("is_day"),
        },
        "daily": {
            "uv_index_max": _first(daily.get("uv_index_max") or []),
            "precipitation_sum_mm": _first(daily.get("precipitation_sum") or []),
            "sunrise": _first(daily.get("sunrise") or []),
            "sunset": _first(daily.get("sunset") or []),
        },
        "hourly": _hourly_slice(weather_data),
        "forecast": _forecast_from_open_meteo(weather_data),
    }


def _forecast_from_weatherapi(data):
    forecast_days = ((data.get("forecast") or {}).get("forecastday")) or []
    rows = []
    for item in forecast_days:
        day = item.get("day") or {}
        astro = item.get("astro") or {}
        condition = (day.get("condition") or {}).get("text") or "Mixed Conditions"
        rows.append(
            {
                "date": item.get("date"),
                "condition": condition,
                "weather_code": None,
                "temperature_max_c": _float_or_none(day.get("maxtemp_c")),
                "temperature_min_c": _float_or_none(day.get("mintemp_c")),
                "uv_index_max": _float_or_none(day.get("uv")),
                "precipitation_sum_mm": _float_or_none(day.get("totalprecip_mm")),
                "sunrise": astro.get("sunrise"),
                "sunset": astro.get("sunset"),
            }
        )
    return rows


def _fetch_weatherapi(api_key, location_name, timeout, latitude=None, longitude=None):
    location_query = (
        f"{latitude},{longitude}"
        if latitude is not None and longitude is not None
        else _normalize_location_name(location_name)
    )
    url = _build_url(
        "https://api.weatherapi.com/v1/forecast.json",
        {"key": api_key, "q": location_query, "days": 7, "aqi": "no", "alerts": "no"},
    )
    data = _get_json(url, timeout)
    location = data.get("location") or {}
    current = data.get("current") or {}
    condition = (current.get("condition") or {}).get("text") or "Mixed Conditions"
    forecast = _forecast_from_weatherapi(data)
    today = forecast[0] if forecast else {}
    location_payload = {
        "name": location.get("name") or _normalize_location_name(location_name),
        "admin1": location.get("region") or "",
        "country": location.get("country") or "",
        "latitude": _float_or_none(location.get("lat")),
        "longitude": _float_or_none(location.get("lon")),
        "timezone": location.get("tz_id") or "Australia/Perth",
    }

    return {
        "source": "weatherapi",
        "source_label": "Live weather",
        "status": "ok",
        "note": "Live weather from WeatherAPI",
        "location": {**location_payload, "label": _location_label(location_payload)},
        "current": {
            "time": current.get("last_updated"),
            "temperature_c": _float_or_none(current.get("temp_c")),
            "humidity_percent": _float_or_none(current.get("humidity")),
            "wind_speed_kmh": _float_or_none(current.get("wind_kph")),
            "cloud_cover_percent": _float_or_none(current.get("cloud")),
            "uv_index": _float_or_none(current.get("uv")),
            "precipitation_mm": _float_or_none(current.get("precip_mm")),
            "rain_mm": _float_or_none(current.get("precip_mm")),
            "weather_code": None,
            "condition": condition,
            "is_day": current.get("is_day"),
        },
        "daily": {
            "uv_index_max": today.get("uv_index_max"),
            "precipitation_sum_mm": today.get("precipitation_sum_mm"),
            "sunrise": today.get("sunrise"),
            "sunset": today.get("sunset"),
        },
        "hourly": [],
        "forecast": forecast,
    }


def fetch_weather_summary(
    location_name=None,
    timeout=4,
    latitude=None,
    longitude=None,
    api_key=None,
):
    api_key = api_key or os.getenv("WEATHER_API_KEY", "")
    try:
        if api_key:
            try:
                return _fetch_weatherapi(api_key, location_name, timeout, latitude, longitude)
            except (HTTPError, URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError):
                return _fetch_open_meteo(location_name, timeout, latitude, longitude)
        return _fetch_open_meteo(location_name, timeout, latitude, longitude)
    except ValueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as err:
        return _unavailable_weather(location_name, f"Weather unavailable: {err}")
