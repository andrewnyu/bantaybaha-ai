import math
from functools import lru_cache
from pathlib import Path
from typing import Tuple

import requests
from django.conf import settings
from shapely.geometry import Point, shape

from core.geo import haversine_km

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RISK_DATA_DIR = Path(__file__).resolve().parent / "data"
NEGROS_DATA_DIR = PROJECT_ROOT / "data"
RISK_POLYGON_FALLBACK = RISK_DATA_DIR / "flood_zones.geojson"
NEGROS_RIVERS_PATH = NEGROS_DATA_DIR / "negros_rivers.geojson"
NEGROS_DEM_PATH = NEGROS_DATA_DIR / "negros_dem.tif"
OPENWEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall"
OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
OPENWEATHER_TIMEOUT_SECONDS = 5
OPEN_ELEVATION_TIMEOUT_SECONDS = 5


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


@lru_cache(maxsize=1)
def load_flood_zone_polygons() -> list:
    if not RISK_POLYGON_FALLBACK.exists():
        return []
    payload = RISK_POLYGON_FALLBACK.read_text()
    import json

    data = json.loads(payload)
    return [shape(feature["geometry"]) for feature in data.get("features", [])]


def _river_union_geometry() -> object | None:
    if not NEGROS_RIVERS_PATH.exists():
        return None

    try:
        import geopandas as gpd

        gdf = gpd.read_file(str(NEGROS_RIVERS_PATH))
        if gdf.empty:
            return None

        gdf = gdf[gdf.geometry.notna()]
        if gdf.empty:
            return None

        return gdf.geometry.unary_union
    except Exception:
        return None


@lru_cache(maxsize=1)
def load_river_union() -> object | None:
    union = _river_union_geometry()
    if union is None:
        return None
    return union


@lru_cache(maxsize=1)
def _load_river_points_fallback() -> list[tuple[float, float]]:
    points_path = RISK_DATA_DIR / "river_points.json"
    if not points_path.exists():
        return []
    import json

    payload = json.loads(points_path.read_text())
    return [(item["lat"], item["lng"]) for item in payload.get("points", [])]


def _safe_openweather_params(lat: float, lng: float) -> dict:
    api_key = getattr(settings, "OPENWEATHER_API_KEY", "")
    return {
        "lat": lat,
        "lon": lng,
        "exclude": "minutely,daily,alerts",
        "appid": api_key,
        "units": "metric",
    }


def _fallback_rainfall_mm(hours: int) -> float:
    return 7.5 * hours


def simulate_rainfall_mm(hours: int) -> float:
    # Deterministic fallback when no API key / call fails.
    return round(_fallback_rainfall_mm(hours), 1)


def get_forecast_rainfall_mm(lat: float, lng: float, hours: int) -> float:
    api_key = getattr(settings, "OPENWEATHER_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        return simulate_rainfall_mm(hours)

    params = _safe_openweather_params(lat, lng)

    try:
        response = requests.get(
            OPENWEATHER_URL,
            params=params,
            timeout=OPENWEATHER_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return simulate_rainfall_mm(hours)

        payload = response.json()
        hourly = payload.get("hourly", [])
        if not hourly:
            return simulate_rainfall_mm(hours)

        safe_hours = max(1, min(6, int(hours)))
        total = 0.0
        for i in range(min(safe_hours, len(hourly))):
            hour_bucket = hourly[i]
            rain = hour_bucket.get("rain", {}) if isinstance(hour_bucket, dict) else {}
            total += float(rain.get("1h", 0.0) or 0.0)

        return round(total, 1)
    except Exception:
        return simulate_rainfall_mm(hours)


def _simulate_elevation_m(lat: float, lng: float) -> float:
    raw = 30 + (math.sin(lat * 3.5) + 1) * 22 + (math.cos(lng * 3.2) + 1) * 28
    return round(clamp(raw, 2.0, 180.0), 1)


def get_elevation_meters(lat: float, lng: float, allow_remote_lookup: bool = True) -> float:
    if NEGROS_DEM_PATH.exists():
        try:
            import rasterio

            with rasterio.open(NEGROS_DEM_PATH) as src:
                sample = list(src.sample([(lng, lat)]))[0]
                elevation = float(sample[0]) if sample is not None else None
                if elevation is not None and not math.isnan(elevation):
                    return round(clamp(elevation, 0.0, 5000.0), 1)
        except Exception:
            pass

    if allow_remote_lookup:
        try:
            response = requests.get(
                OPEN_ELEVATION_URL,
                params={"locations": f"{lat},{lng}"},
                timeout=OPEN_ELEVATION_TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                payload = response.json()
                results = payload.get("results", [])
                if results:
                    value = float(results[0].get("elevation", 0.0))
                    return round(clamp(value, 0.0, 5000.0), 1)
        except Exception:
            pass

    return _simulate_elevation_m(lat, lng)


def elevation_factor(elevation_m: float) -> float:
    if elevation_m < 20:
        return 100.0
    if elevation_m < 50:
        return 65.0
    return 35.0


def distance_to_nearest_river_km(lat: float, lng: float) -> float:
    river_union = load_river_union()
    if river_union is not None:
        point = Point(lng, lat)
        return clamp(point.distance(river_union) * 111.0, 0.0, 999.0)

    fallback_points = _load_river_points_fallback()
    if not fallback_points:
        return 999.0

    distances = [haversine_km(lat, lng, r_lat, r_lng) for r_lat, r_lng in fallback_points]
    return min(distances) if distances else 999.0


def river_proximity_factor(distance_km: float) -> float:
    if distance_km <= 0.05:
        return 100.0
    if distance_km >= 20.0:
        return 0.0
    return clamp(((20.0 - distance_km) / 19.95) * 100.0, 0.0, 100.0)


def historical_flood_factor(lat: float, lng: float) -> tuple[float, bool]:
    polygons = load_flood_zone_polygons()
    if not polygons:
        return 0.0, False

    point = Point(lng, lat)
    if any(poly.contains(point) for poly in polygons):
        return 100.0, True

    min_deg_distance = min(poly.distance(point) for poly in polygons)
    approx_km = min_deg_distance * 111.0

    if approx_km < 1.0:
        return 60.0, False
    if approx_km < 4.0:
        return 30.0, False
    return 8.0, False


def classify_risk(score: int) -> str:
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def estimate_flood_risk(lat: float, lng: float, hours: int = 3) -> dict:
    safe_hours = int(clamp(hours, 1, 6))

    rainfall_mm = _forecast_rainfall_mm(lat, lng, safe_hours)
    elevation_m = get_elevation_meters(lat, lng, allow_remote_lookup=True)
    elev_factor = elevation_factor(elevation_m)

    river_distance = distance_to_nearest_river_km(lat, lng)
    river_factor = river_proximity_factor(river_distance)

    hist_factor, in_flood_zone = historical_flood_factor(lat, lng)

    # Weighted heuristic score for 1-6 hour flood outlook.
    raw_score = (
        (rainfall_mm * 0.5)
        + (river_factor * 0.2)
        + (elev_factor * 0.2)
        + (hist_factor * 0.1)
    )
    risk_score = int(round(clamp(raw_score, 0.0, 100.0)))
    risk_level = classify_risk(risk_score)

    explanation = [
        f"Rainfall next {safe_hours}h: {rainfall_mm} mm",
        f"Elevation: {elevation_m} m",
        f"Distance to nearest river: {round(river_distance, 3)} km",
    ]

    if in_flood_zone:
        explanation.append("Inside historical flood zone")
    elif hist_factor >= 30:
        explanation.append("Near historical flood zone")

    if risk_level == "HIGH":
        explanation.append("High flood risk conditions detected")

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "explanation": explanation,
    }
