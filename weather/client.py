import math
import time
from functools import lru_cache
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

OPENWEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall"
OPENWEATHER_TIMEMACHINE_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"
OPENWEATHER_TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = 600


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _hourly_cache_key(lat: float, lng: float, mode: str = "live", reference_time: int | None = None) -> str:
    return f"{round(lat, 5)}:{round(lng, 5)}:{mode}:{reference_time or 'now'}"


_hourly_cache: dict[str, tuple[float, list[float]]] = {}


def parse_reference_time(reference_time: str | int | float | None) -> int:
    if reference_time is None:
        raise ValueError("reference_time is required for historical mode")

    if isinstance(reference_time, (int, float)):
        return int(reference_time)

    value = str(reference_time).strip()
    if not value:
        raise ValueError("reference_time is required for historical mode")
    if value.isdigit():
        epoch = int(value)
        return int(epoch / 1000) if len(value) >= 13 else epoch

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "reference_time must be unix epoch seconds or ISO format, e.g. 2026-02-28T10:00:00"
        ) from exc

    if dt.tzinfo is None:
        tz_name = getattr(settings, "TIME_ZONE", "Asia/Manila") or "Asia/Manila"
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return int(dt.timestamp())


def _extract_hourly_records(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    hourly = payload.get("hourly")
    if isinstance(hourly, list):
        return hourly

    data = payload.get("data")
    return list(data) if isinstance(data, list) else []


def _fallback_hourly_rain(lat: float, lng: float, hours: int, reference_time: int | None = None) -> list[float]:
    # Deterministic fallback used when no API key or request fails.
    safe_hours = max(1, min(6, int(hours)))
    key = f"{lat:.4f}:{lng:.4f}:{reference_time or 0}"
    base = 5.0 + (abs(hash(key) % 12) * 0.4)
    return [round(clamp(base - (i * 0.65), 0.0, 50.0), 1) for i in range(safe_hours)]


def get_hourly_rain(
    lat: float,
    lng: float,
    hours: int = 6,
    weather_mode: str = "live",
    reference_time: str | int | float | None = None,
) -> list[float]:
    safe_hours = max(1, min(6, int(hours)))
    mode = (str(weather_mode).strip().lower() or "live")
    is_historical = mode == "historical"
    reference_epoch: int | None = parse_reference_time(reference_time) if is_historical else None
    key = _hourly_cache_key(lat, lng, "historical" if is_historical else "live", reference_epoch)
    now = time.time()

    cached = _hourly_cache.get(key)
    if cached:
        cached_at, values = cached
        if now - cached_at < WEATHER_CACHE_SECONDS and len(values) >= safe_hours:
            return [round(float(v), 1) for v in values[:safe_hours]]

    api_key = getattr(settings, "OPENWEATHER_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        hourly = _fallback_hourly_rain(lat, lng, safe_hours, reference_epoch)
        _hourly_cache[key] = (now, hourly)
        return hourly

    params = {
        "lat": lat,
        "lon": lng,
        "appid": api_key,
        "units": "metric",
    }
    endpoint = OPENWEATHER_URL
    if is_historical:
        params["dt"] = reference_epoch
        endpoint = OPENWEATHER_TIMEMACHINE_URL
    else:
        params["exclude"] = "minutely,daily,alerts"

    try:
        response = requests.get(endpoint, params=params, timeout=OPENWEATHER_TIMEOUT_SECONDS)
        if response.status_code != 200:
            hourly = _fallback_hourly_rain(lat, lng, safe_hours, reference_epoch)
            _hourly_cache[key] = (now, hourly)
            return hourly

        payload = response.json()
        hourly_records = _extract_hourly_records(payload)
        values: list[float] = []
        for index in range(safe_hours):
            if index >= len(hourly_records):
                break
            entry = hourly_records[index] if isinstance(hourly_records[index], dict) else {}
            rain_bucket = entry.get("rain", {}) if isinstance(entry, dict) else {}
            values.append(float(rain_bucket.get("1h", 0.0) or 0.0))

        if not values:
            values = _fallback_hourly_rain(lat, lng, safe_hours, reference_epoch)

        while len(values) < safe_hours:
            values.append(0.0)

        hourly = [round(float(v), 1) for v in values[:safe_hours]]
        _hourly_cache[key] = (now, hourly)
        return hourly
    except Exception:
        hourly = _fallback_hourly_rain(lat, lng, safe_hours, reference_epoch)
        _hourly_cache[key] = (now, hourly)
        return hourly


def get_hourly_rain_sum(
    lat: float,
    lng: float,
    hours: int = 6,
    weather_mode: str = "live",
    reference_time: str | int | float | None = None,
) -> float:
    return round(
        sum(
            get_hourly_rain(
                lat=lat,
                lng=lng,
                hours=hours,
                weather_mode=weather_mode,
                reference_time=reference_time,
            )
        ),
        1,
    )
