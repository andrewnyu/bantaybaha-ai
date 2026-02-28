from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from core.geo import haversine_km
from risk.risk_engine import (
    classify_risk,
    distance_to_nearest_river_km,
    get_elevation_meters,
    get_forecast_rainfall_sum_mm,
)
from risk.risk_engine import estimate_flood_risk
from risk.upstream import compute_upstream_rain_index

from shapely.geometry import LineString, shape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEGROS_RIVERS_PATH = PROJECT_ROOT / "data" / "negros_rivers.geojson"
NEGROS_BOUNDS = {
    "south": 9.0,
    "north": 10.95,
    "west": 122.15,
    "east": 123.55,
}

RIVER_RISK_THRESHOLD = 60.0
ROAD_HAZARD_THRESHOLD = 6.0
MAX_ROAD_EDGES_TO_EVALUATE = 700


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _generate_sample_points(max_points: int) -> list[tuple[float, float]]:
    bounded_n = int(_clamp(int(max_points), 20, 600))
    lat_span = NEGROS_BOUNDS["north"] - NEGROS_BOUNDS["south"]
    lng_span = NEGROS_BOUNDS["east"] - NEGROS_BOUNDS["west"]

    # Keep roughly square-ish cells.
    cols = max(
        8,
        int(
            math.sqrt(
                bounded_n * (lng_span / max(lat_span, 0.0001))
            )
        ),
    )
    rows = max(6, int(math.ceil(bounded_n / cols)))
    lat_step = lat_span / max(rows - 1, 1)
    lng_step = lng_span / max(cols - 1, 1)

    points = []
    for i in range(rows):
        lat = NEGROS_BOUNDS["south"] + (lat_step * i)
        for j in range(cols):
            lng = NEGROS_BOUNDS["west"] + (lng_step * j)
            points.append((round(lat, 6), round(lng, 6)))
            if len(points) >= bounded_n:
                return points
    return points


def _point_in_bounds(lat: float, lng: float) -> bool:
    return (
        NEGROS_BOUNDS["south"] <= lat <= NEGROS_BOUNDS["north"]
        and NEGROS_BOUNDS["west"] <= lng <= NEGROS_BOUNDS["east"]
    )


def _load_river_lines() -> list[LineString]:
    if not NEGROS_RIVERS_PATH.exists():
        return []

    payload = json.loads(NEGROS_RIVERS_PATH.read_text())
    features = payload.get("features", [])

    lines: list[LineString] = []
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue

        geom = shape(geometry)
        if geom.is_empty:
            continue

        if geom.geom_type == "LineString":
            lines.append(geom)
        elif geom.geom_type == "MultiLineString":
            lines.extend([part for part in geom.geoms if not part.is_empty])

    return lines


def _segment_midpoint(line: LineString) -> tuple[float, float]:
    if line.geom_type != "LineString":
        line = line.interpolate(0.5, normalized=True)
        return (line.y, line.x)

    midpoint = line.interpolate(0.5, normalized=True)
    return (round(float(midpoint.y), 6), round(float(midpoint.x), 6))


def _river_risk_score(lat: float, lng: float, hours: int) -> float:
    payload = estimate_flood_risk(lat=lat, lng=lng, hours=hours)
    return float(payload["risk_score"])


def _road_hazard_score(
    lat: float,
    lng: float,
    hours: int,
    upstream_norm: float,
) -> float:
    rainfall = get_forecast_rainfall_sum_mm(lat, lng, hours)
    hazard = 0.0
    elevation = 9999
    try:
        elevation = get_elevation_meters(lat, lng, allow_remote_lookup=False)
    except Exception:
        elevation = 30

    if elevation < 20:
        hazard += 2

    distance_to_river_km = distance_to_nearest_river_km(lat, lng)
    if distance_to_river_km <= 0.25:
        hazard += 2
        hazard += (upstream_norm / 100.0) * 4.0
    elif distance_to_river_km <= 0.75:
        hazard += (upstream_norm / 100.0) * 2.0

    if rainfall > 30:
        hazard += 1

    return float(_clamp(hazard, 0.0, 100.0))


def _hazard_level(hazard: float) -> str:
    if hazard >= 12:
        return "HIGH"
    if hazard >= 6:
        return "MEDIUM"
    return "LOW"


def build_risk_area_payload(
    hours: int = 3,
    severity: str = "high",
    max_points: int = 140,
    include_rivers: bool = True,
    include_roads: bool = True,
) -> dict[str, Any]:
    start = time.time()
    hours_int = int(_clamp(hours, 1, 6))
    max_points = int(_clamp(max_points, 20, 600))
    severity = "all" if str(severity).lower() == "all" else "high"
    score_threshold = 65 if severity == "high" else 0
    warnings: list[str] = []
    if include_rivers and not NEGROS_RIVERS_PATH.exists():
        warnings.append("River GeoJSON unavailable for Negros overlay.")
        include_rivers = False

    sample_points = []
    sampled_points_total = 0
    for lat, lng in _generate_sample_points(max_points):
        if not _point_in_bounds(lat, lng):
            continue

        payload = estimate_flood_risk(lat=lat, lng=lng, hours=hours_int)
        sampled_points_total += 1
        upstream_nodes = payload.get("upstream_summary", {})
        dominant_points = upstream_nodes.get("dominant_upstream_points") or []
        upstream_node_id = dominant_points[0].get("node_id") if dominant_points else None

        if payload["risk_score"] >= score_threshold:
            sample_points.append(
                {
                    "lat": lat,
                    "lng": lng,
                    "risk_score": payload["risk_score"],
                    "risk_level": payload["risk_level"],
                    "expected_peak_in_hours": payload["expected_peak_in_hours"],
                    "upstream_node_id": upstream_node_id,
                }
            )

    rivers_payload = {"type": "FeatureCollection", "features": []}
    if include_rivers:
        for line in _load_river_lines():
            mid_lat, mid_lng = _segment_midpoint(line)
            if not _point_in_bounds(mid_lat, mid_lng):
                continue

            score = _river_risk_score(mid_lat, mid_lng, hours_int)
            if score < RIVER_RISK_THRESHOLD:
                continue

            coords = [[round(float(x), 6), round(float(y), 6)] for x, y in line.coords]
            if len(coords) < 2:
                continue
            rivers_payload["features"].append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "risk_score": round(score, 2),
                        "risk_level": classify_risk(int(round(score))),
                        "lat": mid_lat,
                        "lng": mid_lng,
                    },
                }
            )

    roads_payload = {"type": "FeatureCollection", "features": []}
    if include_roads:
        from routing.routing_engine import load_graph

        try:
            graph = load_graph()
        except Exception as exc:
            warnings.append(f"Road graph unavailable: {str(exc)}")
            include_roads = False
        else:
            edges = list(graph.edges(keys=True, data=True))
            if len(edges) > MAX_ROAD_EDGES_TO_EVALUATE:
                stride = max(1, math.ceil(len(edges) / MAX_ROAD_EDGES_TO_EVALUATE))
                edges = edges[::stride]

            for u, v, _key, edge_data in edges:
                u_attrs = graph.nodes[u]
                v_attrs = graph.nodes[v]
                u_lat = float(u_attrs.get("y", 0.0))
                u_lng = float(u_attrs.get("x", 0.0))
                v_lat = float(v_attrs.get("y", 0.0))
                v_lng = float(v_attrs.get("x", 0.0))
                if not (_point_in_bounds(u_lat, u_lng) and _point_in_bounds(v_lat, v_lng)):
                    continue

                mid_lat = (u_lat + v_lat) / 2
                mid_lng = (u_lng + v_lng) / 2
                upstream = compute_upstream_rain_index(mid_lat, mid_lng, horizon_hours=hours_int)
                upstream_norm = float(upstream.get("upstream_rain_index_norm", 0.0))
                hazard = _road_hazard_score(mid_lat, mid_lng, hours_int, upstream_norm)
                if hazard < ROAD_HAZARD_THRESHOLD:
                    continue

                length = float(edge_data.get("length", haversine_km(u_lat, u_lng, v_lat, v_lng) * 1000))
                roads_payload["features"].append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [round(u_lng, 6), round(u_lat, 6)],
                                [round(v_lng, 6), round(v_lat, 6)],
                            ],
                        },
                        "properties": {
                            "risk_score": round(hazard, 2),
                            "risk_level": _hazard_level(hazard),
                            "hazard_score": round(hazard, 2),
                            "length_m": round(length, 2),
                        },
                    }
                )

    runtime_ms = round((time.time() - start) * 1000, 1)
    return {
        "area_points": sample_points,
        "rivers": rivers_payload if include_rivers else {"type": "FeatureCollection", "features": []},
        "roads": roads_payload if include_roads else {"type": "FeatureCollection", "features": []},
        "meta": {
            "hours": hours_int,
            "source": "negros_sample_grid",
            "sampled_points": sampled_points_total,
            "max_points": max_points,
            "thresholds": {
                "point_risk_threshold": score_threshold,
                "river_risk_threshold": RIVER_RISK_THRESHOLD,
                "road_hazard_threshold": ROAD_HAZARD_THRESHOLD,
            },
            "include_rivers": bool(include_rivers),
            "include_roads": bool(include_roads),
            "warnings": warnings,
            "runtime_ms": runtime_ms,
        },
    }


def build_river_only_meta() -> dict[str, Any]:
    return {
        "bounds": NEGROS_BOUNDS,
        "river_source": str(NEGROS_RIVERS_PATH),
    }
