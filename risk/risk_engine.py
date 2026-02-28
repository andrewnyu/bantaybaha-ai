import math
from functools import lru_cache
from pathlib import Path

from core.geo import haversine_km
from weather.client import get_hourly_rain_sum
from risk.upstream import compute_upstream_rain_index

from shapely.geometry import Point, shape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RISK_DATA_DIR = Path(__file__).resolve().parent / "data"
NEGROS_DATA_DIR = PROJECT_ROOT / "data"
PROJECT_DATA_DIR = PROJECT_ROOT / "data"
RISK_POLYGON_FALLBACK = RISK_DATA_DIR / "flood_zones.geojson"
NEGROS_RIVERS_PATH = NEGROS_DATA_DIR / "negros_rivers.geojson"
RIVER_SAMPLE_POINTS_PATH = PROJECT_DATA_DIR / "river_sample_points.json"
NEGROS_ROAD_GRAPH_PATH = PROJECT_DATA_DIR / "negros_graph.graphml"
NEGROS_DEM_PATH = NEGROS_DATA_DIR / "negros_dem.tif"
OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
OPEN_ELEVATION_TIMEOUT_SECONDS = 5
RIVER_METRIC_CRS = "EPSG:3857"
_MISSING_RIVER_DISTANCE_WARNED = False


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _load_geojson_payload(path: Path) -> list:
    if not path.exists():
        return []
    payload = path.read_text()
    import json

    data = json.loads(payload)
    return data.get("features", [])


@lru_cache(maxsize=1)
def load_flood_zone_polygons() -> list:
    features = _load_geojson_payload(RISK_POLYGON_FALLBACK)
    return [shape(feature["geometry"]) for feature in features]


def _load_geojson_union_as_metric_geometry():
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

        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        return gdf.to_crs(RIVER_METRIC_CRS).geometry.unary_union
    except Exception:
        return None


@lru_cache(maxsize=1)
def load_river_union() -> object | None:
    union = _load_geojson_union_as_metric_geometry()
    if union is None:
        return None
    return union


def _load_river_points_fallback() -> list[tuple[float, float]]:
    candidate_paths = [RIVER_SAMPLE_POINTS_PATH]
    import json

    for points_path in candidate_paths:
        if not points_path.exists():
            continue
        payload = json.loads(points_path.read_text())
        points = payload.get("points", [])
        if not points:
            continue
        return [(item.get("lat"), item.get("lng")) for item in points if item.get("lat") is not None and item.get("lng") is not None]

    return _load_river_proxy_points_from_graph()


def _load_river_proxy_points_from_graph(limit: int = 320) -> list[tuple[float, float]]:
    if not NEGROS_ROAD_GRAPH_PATH.exists():
        return []

    try:
        import osmnx as ox
        graph = ox.load_graphml(NEGROS_ROAD_GRAPH_PATH)
    except Exception:
        return []

    points: list[tuple[float, float]] = []
    for _, attrs in graph.nodes(data=True):
        node_lat = attrs.get("y")
        node_lng = attrs.get("x")
        if node_lat is None or node_lng is None:
            continue
        points.append((float(node_lat), float(node_lng)))
        if len(points) >= limit:
            break

    return points


def get_forecast_rainfall_sum_mm(
    lat: float,
    lng: float,
    hours: int,
    weather_mode: str = "live",
    reference_time: str | int | float | None = None,
    demo_rainfall: object | None = None,
) -> float:
    return get_hourly_rain_sum(
        lat=lat,
        lng=lng,
        hours=max(1, min(6, int(hours))),
        weather_mode=weather_mode,
        reference_time=reference_time,
        demo_rainfall=demo_rainfall,
    )


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
            import requests

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


def estimate_flood_depth_m(
    local_rain_mm: float,
    upstream_norm: float,
    elevation_m: float,
) -> float:
    rain_signal = clamp(local_rain_mm / 120.0, 0.0, 1.8)
    upstream_signal = clamp(upstream_norm / 100.0, 0.0, 1.0) * 0.8
    elevation_scale = clamp(1.2 - elevation_m / 250.0, 0.25, 1.0)

    depth = (0.55 * rain_signal + 0.35 * upstream_signal) * elevation_scale
    return round(clamp(depth, 0.0, 3.0), 2)


def classify_flood_depth(level_m: float) -> str:
    if level_m >= 2.0:
        return "2-storey-height"
    if level_m >= 1.0:
        return "above-head"
    if level_m >= 0.5:
        return "chest"
    if level_m >= 0.2:
        return "knee"
    return "shallow"


def distance_to_nearest_river_km(lat: float, lng: float) -> float:
    river_union = load_river_union()
    if river_union is not None:
        try:
            from pyproj import Transformer

            to_metric = Transformer.from_crs("EPSG:4326", RIVER_METRIC_CRS, always_xy=True)
            metric_lng, metric_lat = to_metric.transform(lng, lat)
            point = Point(metric_lng, metric_lat)
            return clamp(point.distance(river_union) / 1000.0, 0.0, 999.0)
        except Exception:
            # Fall back to approximate distance in degrees if projection fails.
            pass

    fallback_points = _load_river_points_fallback()
    if not fallback_points:
        global _MISSING_RIVER_DISTANCE_WARNED
        if not _MISSING_RIVER_DISTANCE_WARNED:
            print(
                "No river dataset available (Negros GeoJSON/sample points/road graph); "
                "river distance fallback returned 999 km."
            )
            _MISSING_RIVER_DISTANCE_WARNED = True
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


def estimate_flood_risk(
    lat: float,
    lng: float,
    hours: int = 3,
    weather_mode: str = "live",
    reference_time: str | int | float | None = None,
    demo_rainfall: object | None = None,
    demo_upstream_rainfall: dict[str, list[float]] | None = None,
) -> dict:
    safe_hours = int(clamp(hours, 1, 6))

    local_rain_3h = get_forecast_rainfall_sum_mm(
        lat=lat,
        lng=lng,
        hours=safe_hours,
        weather_mode=weather_mode,
        reference_time=reference_time,
        demo_rainfall=demo_rainfall,
    )
    elevation_m = get_elevation_meters(lat, lng, allow_remote_lookup=True)
    elev_factor = elevation_factor(elevation_m)
    river_distance = distance_to_nearest_river_km(lat, lng)
    river_factor = river_proximity_factor(river_distance)
    hist_factor, in_flood_zone = historical_flood_factor(lat, lng)

    upstream = compute_upstream_rain_index(
        lat,
        lng,
        horizon_hours=safe_hours,
        weather_mode=weather_mode,
        reference_time=reference_time,
        demo_rainfall=demo_rainfall,
        demo_upstream_rainfall=demo_upstream_rainfall,
    )
    upstream_norm = upstream["upstream_rain_index_norm"]

    raw_score = (
        (local_rain_3h * 0.35)
        + (upstream_norm * 0.35)
        + (river_factor * 0.15)
        + (elev_factor * 0.1)
        + (hist_factor * 0.05)
    )
    risk_score = int(round(clamp(raw_score, 0.0, 100.0)))
    risk_level = classify_risk(risk_score)

    expected_peak = upstream.get("expected_peak_in_hours")
    explanation = [
        f"Rainfall next {safe_hours}h: {local_rain_3h} mm",
        f"Elevation: {elevation_m} m",
        f"Distance to nearest river: {round(river_distance, 3)} km",
        f"Upstream risk index: {upstream['upstream_rain_index']} (normalized {upstream['upstream_rain_index_norm']})",
    ]

    dominant_points = upstream.get("dominant_upstream_points") or []
    estimated_water_level = estimate_flood_depth_m(local_rain_3h, upstream_norm, elevation_m)
    water_level_zone = classify_flood_depth(estimated_water_level)
    if dominant_points:
        top = dominant_points[0]
        explanation.append(
            f"Heavy rainfall detected upstream in watershed ({top['rain_sum']} mm) near the river network."
        )

    if in_flood_zone:
        explanation.append("Inside historical flood zone")
    elif hist_factor >= 30:
        explanation.append("Near historical flood zone")

    if risk_level == "HIGH":
        explanation.append("High flood risk conditions detected")

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "expected_peak_in_hours": expected_peak,
        "estimated_flood_level_m": estimated_water_level,
        "flood_level_zone": water_level_zone,
        "explanation": explanation,
        "upstream_summary": upstream,
    }
