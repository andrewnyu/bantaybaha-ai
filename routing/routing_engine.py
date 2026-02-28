import json
from functools import lru_cache
from pathlib import Path

import networkx as nx

from core.geo import haversine_km
from risk.risk_engine import historical_flood_factor, river_proximity_factor
from risk.risk_engine import distance_to_nearest_river_km

DATA_DIR = Path(__file__).resolve().parent / "data"


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


@lru_cache(maxsize=1)
def load_graph_payload() -> dict:
    graph_path = DATA_DIR / "road_graph.json"
    return json.loads(graph_path.read_text())


@lru_cache(maxsize=1)
def build_graph() -> nx.Graph:
    payload = load_graph_payload()
    graph = nx.Graph()

    for node_id, node_data in payload["nodes"].items():
        graph.add_node(node_id, lat=node_data["lat"], lng=node_data["lng"])

    for edge in payload["edges"]:
        start = edge["from"]
        end = edge["to"]

        start_node = payload["nodes"][start]
        end_node = payload["nodes"][end]

        distance = edge.get(
            "distance",
            haversine_km(
                start_node["lat"],
                start_node["lng"],
                end_node["lat"],
                end_node["lng"],
            ),
        )

        hazard = edge.get("hazard_score")
        if hazard is None:
            midpoint_lat = (start_node["lat"] + end_node["lat"]) / 2
            midpoint_lng = (start_node["lng"] + end_node["lng"]) / 2
            historical_factor, _ = historical_flood_factor(midpoint_lat, midpoint_lng)
            river_factor = river_proximity_factor(
                distance_to_nearest_river_km(midpoint_lat, midpoint_lng)
            )
            hazard = clamp((historical_factor * 0.6) + (river_factor * 0.4), 0.0, 100.0)

        graph.add_edge(start, end, distance=float(distance), hazard_score=float(hazard))

    return graph


def nearest_node_id(graph: nx.Graph, lat: float, lng: float) -> str:
    nearest = None
    nearest_distance = float("inf")

    for node_id, attrs in graph.nodes(data=True):
        km = haversine_km(lat, lng, attrs["lat"], attrs["lng"])
        if km < nearest_distance:
            nearest = node_id
            nearest_distance = km

    if nearest is None:
        raise ValueError("Graph has no nodes")
    return nearest


def compute_safe_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    safety_weight: float = 2.0,
) -> dict:
    graph = build_graph()

    origin_node = nearest_node_id(graph, origin_lat, origin_lng)
    dest_node = nearest_node_id(graph, dest_lat, dest_lng)

    def edge_cost(start, end, attrs):
        return attrs["distance"] + (attrs["hazard_score"] * safety_weight)

    path = nx.shortest_path(graph, source=origin_node, target=dest_node, weight=edge_cost)

    route = []
    total_distance = 0.0
    hazard_exposure = 0.0

    for node_id in path:
        route.append(
            {
                "lat": graph.nodes[node_id]["lat"],
                "lng": graph.nodes[node_id]["lng"],
            }
        )

    for index in range(len(path) - 1):
        edge_data = graph[path[index]][path[index + 1]]
        total_distance += edge_data["distance"]
        hazard_exposure += edge_data["hazard_score"]

    return {
        "route": route,
        "total_distance": round(total_distance, 3),
        "hazard_exposure": round(hazard_exposure, 3),
        "origin_node": origin_node,
        "destination_node": dest_node,
    }
