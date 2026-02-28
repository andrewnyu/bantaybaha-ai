import math
import time
from functools import lru_cache
from typing import Iterable

import requests
from django.conf import settings

OPENWEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall"
OPENWEATHER_TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = 600


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _hourly_cache_key(lat: float, lng: float) -> str:
    return f"{round(lat, 5)}:{round(lng, 5)}"


_hourly_cache: dict[str, tuple[float, list[float]]] = {}


def _fallback_hourly_rain(lat: float, lng: float, hours: int) -> list[float]:
    # Deterministic fallback used when no API key or request fails.
    safe_hours = max(1, min(6, int(hours)))
    base = 5.0 + (abs(hash(f"{lat:.4f}:{lng:.4f}") % 12) * 0.4)
    return [round(clamp(base - (i * 0.65), 0.0, 50.0), 1) for i in range(safe_hours)]


def get_hourly_rain(lat: float, lng: float, hours: int = 6) -> list[float]:
    safe_hours = max(1, min(6, int(hours)))
    key = _hourly_cache_key(lat, lng)
    now = time.time()

    cached = _hourly_cache.get(key)
    if cached:
        cached_at, values = cached
        if now - cached_at < WEATHER_CACHE_SECONDS and len(values) >= safe_hours:
            return [round(float(v), 1) for v in values[:safe_hours]]

    api_key = getattr(settings, "OPENWEATHER_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        hourly = _fallback_hourly_rain(lat, lng, safe_hours)
        _hourly_cache[key] = (now, hourly)
        return hourly

    params = {
        "lat": lat,
        "lon": lng,
        "exclude": "minutely,daily,alerts",
        "appid": api_key,
        "units": "metric",
    }

    try:
        response = requests.get(OPENWEATHER_URL, params=params, timeout=OPENWEATHER_TIMEOUT_SECONDS)
        if response.status_code != 200:
            hourly = _fallback_hourly_rain(lat, lng, safe_hours)
            _hourly_cache[key] = (now, hourly)
            return hourly

        payload = response.json()
        hourly_records = payload.get("hourly", []) or []
        values: list[float] = []
        for index in range(safe_hours):
            if index >= len(hourly_records):
                break
            entry = hourly_records[index] if isinstance(hourly_records[index], dict) else {}
            rain_bucket = entry.get("rain", {}) if isinstance(entry, dict) else {}
            values.append(float(rain_bucket.get("1h", 0.0) or 0.0))

        if not values:
            values = _fallback_hourly_rain(lat, lng, safe_hours)

        while len(values) < safe_hours:
            values.append(0.0)

        hourly = [round(float(v), 1) for v in values[:safe_hours]]
        _hourly_cache[key] = (now, hourly)
        return hourly
    except Exception:
        hourly = _fallback_hourly_rain(lat, lng, safe_hours)
        _hourly_cache[key] = (now, hourly)
        return hourly


def get_hourly_rain_sum(lat: float, lng: float, hours: int = 6) -> float:
    return round(sum(get_hourly_rain(lat, lng, hours)), 1)

