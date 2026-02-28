import json
import math
import random
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape

from core.geo import haversine_km

DATA_DIR = Path(__file__).resolve().parent / "data"


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


@lru_cache(maxsize=1)
def load_flood_zone_polygons() -> list:
    geojson_path = DATA_DIR / "flood_zones.geojson"
    payload = json.loads(geojson_path.read_text())
    return [shape(feature["geometry"]) for feature in payload["features"]]


@lru_cache(maxsize=1)
def load_river_points() -> list[tuple[float, float]]:
    points_path = DATA_DIR / "river_points.json"
    payload = json.loads(points_path.read_text())
    return [(item["lat"], item["lng"]) for item in payload["points"]]


def simulate_rainfall_mm(lat: float, lng: float, hours: int) -> float:
    seed = f"{lat:.4f}:{lng:.4f}:{hours}"
    rng = random.Random(seed)
    return round(min(50.0, rng.uniform(0.0, 35.0) + (hours * 2.5)), 1)


def simulate_elevation_m(lat: float, lng: float) -> float:
    # Simple deterministic terrain simulation for MVP demos.
    raw = 20 + (math.sin(lat * 8) + 1) * 20 + (math.cos(lng * 8) + 1) * 25
    return round(clamp(raw, 2.0, 120.0), 1)


def elevation_factor(elevation_m: float) -> float:
    # Lower elevation means higher flood risk.
    return clamp((100.0 - elevation_m) / 100.0 * 100.0, 0.0, 100.0)


def distance_to_nearest_river_km(lat: float, lng: float) -> float:
    distances = [haversine_km(lat, lng, rp_lat, rp_lng) for rp_lat, rp_lng in load_river_points()]
    return min(distances) if distances else 999.0


def river_proximity_factor(distance_km: float) -> float:
    if distance_km <= 0.5:
        return 100.0
    if distance_km >= 10.0:
        return 0.0
    return clamp(((10.0 - distance_km) / 9.5) * 100.0, 0.0, 100.0)


def historical_flood_factor(lat: float, lng: float) -> tuple[float, bool]:
    point = Point(lng, lat)
    polygons = load_flood_zone_polygons()

    if any(poly.contains(point) for poly in polygons):
        return 100.0, True

    min_deg_distance = min(poly.distance(point) for poly in polygons)
    approx_km = min_deg_distance * 111.0

    if approx_km < 1.0:
        return 60.0, False
    if approx_km < 3.0:
        return 30.0, False
    return 5.0, False


def classify_risk(score: int) -> str:
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def estimate_flood_risk(lat: float, lng: float, hours: int = 3) -> dict:
    safe_hours = int(clamp(hours, 1, 6))

    rainfall_mm = simulate_rainfall_mm(lat, lng, safe_hours)
    elevation_m = simulate_elevation_m(lat, lng)
    elev_factor = elevation_factor(elevation_m)
    river_distance = distance_to_nearest_river_km(lat, lng)
    river_factor = river_proximity_factor(river_distance)
    hist_factor, in_flood_zone = historical_flood_factor(lat, lng)

    # Weighted heuristic score for 1-6 hour flood outlook.
    raw_score = (
        (rainfall_mm * 0.5)
        + (elev_factor * 0.2)
        + (river_factor * 0.2)
        + (hist_factor * 0.1)
    )
    risk_score = int(round(clamp(raw_score, 0.0, 100.0)))
    risk_level = classify_risk(risk_score)

    explanation = []
    if rainfall_mm >= 25:
        explanation.append("Heavy rainfall forecast")
    elif rainfall_mm >= 12:
        explanation.append("Moderate rainfall forecast")

    if elev_factor >= 55:
        explanation.append("Low elevation area")

    if river_factor >= 55:
        explanation.append("Close to river")

    if in_flood_zone:
        explanation.append("Inside historical flood zone")
    elif hist_factor >= 30:
        explanation.append("Near historical flood zone")

    if not explanation:
        explanation.append("No major flood risk indicators from current simulation")

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "explanation": explanation,
    }
