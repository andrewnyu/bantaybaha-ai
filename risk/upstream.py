import math
import pickle
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

import networkx as nx

from core.geo import haversine_km
from weather.client import get_hourly_rain_sum

BASE_DIR = Path(__file__).resolve().parents[1]
RIVER_GRAPH_PATH = BASE_DIR / "data" / "negros_river_graph.gpickle"
FLOW_SPEED_MPS = 1.0
DECAY_DISTANCE_M = 20_000

def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def nearest_river_node_id(graph: nx.DiGraph, lat: float, lng: float) -> str | None:
    nearest = None
    nearest_distance = float("inf")

    for node_id, attrs in graph.nodes(data=True):
        node_lat = attrs.get("lat")
        node_lng = attrs.get("lng")
        if node_lat is None or node_lng is None:
            continue
        distance = haversine_km(lat, lng, node_lat, node_lng)
        if distance < nearest_distance:
            nearest = str(node_id)
            nearest_distance = distance

    return nearest


@lru_cache(maxsize=1)
def _load_river_graph() -> nx.DiGraph | None:
    if not RIVER_GRAPH_PATH.exists():
        return None

    try:
        return nx.read_gpickle(RIVER_GRAPH_PATH)
    except Exception:
        try:
            with RIVER_GRAPH_PATH.open("rb") as handle:
                payload = pickle.load(handle)
            if isinstance(payload, nx.Graph):
                return payload
            return None
        except Exception:
            return None


def _travel_distance_to_max(horizon_hours: int) -> float:
    safe_hours = clamp(int(horizon_hours), 1, 6)
    return safe_hours * 3600 * FLOW_SPEED_MPS


def compute_upstream_rain_index(lat: float, lng: float, horizon_hours: int = 6) -> dict:
    horizon_hours = int(clamp(horizon_hours, 1, 6))
    river_graph = _load_river_graph()
    if river_graph is None or river_graph.number_of_nodes() == 0:
        return {
            "upstream_rain_index": 0.0,
            "upstream_rain_index_norm": 0.0,
            "upstream_nodes_used": 0,
            "max_upstream_distance_m": 0.0,
            "dominant_upstream_points": [],
            "expected_peak_in_hours": None,
            "max_distance_m": _travel_distance_to_max(horizon_hours),
        }

    source = nearest_river_node_id(river_graph, lat, lng)
    if source is None:
        return {
            "upstream_rain_index": 0.0,
            "upstream_rain_index_norm": 0.0,
            "upstream_nodes_used": 0,
            "max_upstream_distance_m": 0.0,
            "dominant_upstream_points": [],
            "expected_peak_in_hours": None,
            "max_distance_m": _travel_distance_to_max(horizon_hours),
        }

    max_distance_m = _travel_distance_to_max(horizon_hours)
    upstream_nodes: dict[str, float]
    upstream_nodes = nx.single_source_dijkstra_path_length(
        river_graph.reverse(copy=False), source, cutoff=max_distance_m, weight="length_m"
    )

    total_weighted = 0.0
    dominant_payload = []

    for node_id, distance_m in upstream_nodes.items():
        node_attrs = river_graph.nodes[node_id]
        node_lat = node_attrs.get("lat")
        node_lng = node_attrs.get("lng")
        if node_lat is None or node_lng is None:
            continue

        rain_total = get_hourly_rain_sum(node_lat, node_lng, horizon_hours)
        distance = float(distance_m)
        weight = math.exp(-distance / DECAY_DISTANCE_M)
        weighted_signal = rain_total * weight
        total_weighted += weighted_signal

        dominant_payload.append(
            {
                "lat": node_lat,
                "lng": node_lng,
                "distance_m": round(distance, 1),
                "rain_sum": rain_total,
                "weighted_signal": round(weighted_signal, 3),
                "node_id": str(node_id),
            }
        )

    dominant_payload.sort(key=lambda item: item["weighted_signal"], reverse=True)
    top_points = dominant_payload[:3]

    if dominant_payload:
        top = dominant_payload[0]
        expected_peak_in_hours = round(top["distance_m"] / (FLOW_SPEED_MPS * 3600), 2)
    else:
        expected_peak_in_hours = None

    upstream_nodes_used = len(upstream_nodes)
    max_upstream_distance = max((float(d) for d in upstream_nodes.values()), default=0.0)

    # Simple normalization for 0-100 score; constant can be tuned quickly in demo.
    upstream_rain_index_norm = clamp((total_weighted / 200.0) * 100.0, 0.0, 100.0)

    return {
        "upstream_rain_index": round(total_weighted, 3),
        "upstream_rain_index_norm": round(upstream_rain_index_norm, 3),
        "upstream_nodes_used": upstream_nodes_used,
        "max_upstream_distance_m": round(max_upstream_distance, 1),
        "dominant_upstream_points": top_points,
        "expected_peak_in_hours": expected_peak_in_hours,
        "max_distance_m": round(max_distance_m, 1),
    }
