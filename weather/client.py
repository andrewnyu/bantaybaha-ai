import math
import json
import hashlib
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
DEMO_HOURS_LIMIT = 6


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _demo_rainfall_cache_key(demo_rainfall: list[float] | None) -> str:
    if not demo_rainfall:
        return "demo:none"

    payload = json.dumps([round(float(v), 1) for v in demo_rainfall], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _normalize_node_key(lat: float | str, lng: float | str) -> str:
    return f"{round(float(lat), 5)},{round(float(lng), 5)}"


def parse_demo_upstream_rainfall(raw_demo_rainfall: object) -> dict[str, list[float]]:
    if raw_demo_rainfall is None:
        return {}

    parsed_payload = raw_demo_rainfall
    if isinstance(raw_demo_rainfall, str):
        normalized = raw_demo_rainfall.strip()
        if not normalized:
            return {}

        try:
            parsed_payload = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "demo_upstream_rainfall must be a JSON object or array."
            ) from exc
    elif isinstance(raw_demo_rainfall, dict):
        parsed_payload = raw_demo_rainfall
    elif isinstance(raw_demo_rainfall, (list, tuple)):
        parsed_payload = list(raw_demo_rainfall)
    else:
        raise ValueError("demo_upstream_rainfall must be a JSON array/object.")

    upstream_map: dict[str, list[float]] = {}

    if isinstance(parsed_payload, dict):
        for raw_key, item in parsed_payload.items():
            if not isinstance(raw_key, str) or "," not in raw_key:
                raise ValueError(
                    "demo_upstream_rainfall object keys must be 'lat,lng' strings."
                )

            raw_lat, raw_lng = raw_key.split(",", 1)
            key = _normalize_node_key(raw_lat, raw_lng)
            values = parse_demo_rainfall_values(item)
            upstream_map[key] = values
        return upstream_map

    if not isinstance(parsed_payload, list):
        raise ValueError("demo_upstream_rainfall must be a JSON array or lat/lng map.")

    for index, item in enumerate(parsed_payload):
        if not isinstance(item, dict):
            raise ValueError("Each demo_upstream_rainfall entry must be an object.")

        lat = item.get("lat")
        lng = item.get("lng")
        if lat is None or lng is None:
            raise ValueError(
                "Each demo_upstream_rainfall entry requires lat and lng coordinates."
            )
        rainfall = (
            item.get("demo_rainfall")
            if item.get("demo_rainfall") is not None
            else item.get("rainfall")
        )
        key = _normalize_node_key(lat, lng)
        upstream_map[key] = parse_demo_rainfall_values(rainfall)

    return upstream_map


def _hourly_cache_key(
    lat: float,
    lng: float,
    mode: str = "live",
    reference_time: int | None = None,
    demo_rainfall: list[float] | None = None,
) -> str:
    return (
        f"{round(lat, 5)}:{round(lng, 5)}:{mode}:"
        f"{reference_time or 'now'}:{_demo_rainfall_cache_key(demo_rainfall)}"
    )


def parse_demo_rainfall_values(raw_demo_rainfall: object) -> list[float]:
    if raw_demo_rainfall is None:
        return []

    items: list
    if isinstance(raw_demo_rainfall, str):
        normalized = raw_demo_rainfall.strip()
        if not normalized:
            return []

        if normalized.startswith("[") and normalized.endswith("]"):
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "demo_rainfall must be comma-separated values or a JSON array, e.g. '10,22,45' or '[10,22,45]'"
                ) from exc

            if not isinstance(parsed, list):
                raise ValueError("demo_rainfall must be a list when using JSON array syntax.")

            items = parsed
        else:
            items = normalized.split(",")
    elif isinstance(raw_demo_rainfall, (list, tuple)):
        items = list(raw_demo_rainfall)
    elif isinstance(raw_demo_rainfall, (int, float)):
        items = [raw_demo_rainfall]
    else:
        raise ValueError("demo_rainfall must be a comma string, JSON array, or list of numbers.")

    values: list[float] = []
    for item in items:
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "demo_rainfall contains invalid numeric values. Use comma-separated non-negative numbers only."
            ) from exc

        if value < 0 or not math.isfinite(value):
            raise ValueError("demo_rainfall must contain non-negative numeric values.")
        values.append(round(value, 1))

    return values[:DEMO_HOURS_LIMIT]


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
    demo_rainfall: object | None = None,
) -> list[float]:
    safe_hours = max(1, min(6, int(hours)))
    mode = (str(weather_mode).strip().lower() or "live")
    is_historical = mode == "historical"
    is_demo = mode == "demo"
    demo_values: list[float] = []
    if is_demo:
        demo_values = parse_demo_rainfall_values(demo_rainfall)
        # Normalize early so we return deterministic, deterministic demo behavior regardless of source location.
        if len(demo_values) < safe_hours:
            demo_values = demo_values + [0.0] * (safe_hours - len(demo_values))
        demo_values = demo_values[:safe_hours]
        key = _hourly_cache_key(lat, lng, "demo", None, demo_values)
        cached = _hourly_cache.get(key)
        now = time.time()
        if cached:
            cached_at, cached_values = cached
            if now - cached_at < WEATHER_CACHE_SECONDS and len(cached_values) >= safe_hours:
                return [round(float(v), 1) for v in cached_values[:safe_hours]]

        _hourly_cache[key] = (now, demo_values)
        return demo_values

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
    except ValueError:
        raise
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
    demo_rainfall: object | None = None,
) -> float:
    return round(
        sum(
            get_hourly_rain(
                lat=lat,
                lng=lng,
                hours=hours,
                weather_mode=weather_mode,
                reference_time=reference_time,
                demo_rainfall=demo_rainfall,
            )
        ),
        1,
    )
