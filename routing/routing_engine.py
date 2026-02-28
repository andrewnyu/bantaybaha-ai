from functools import lru_cache
from pathlib import Path

import networkx as nx
import osmnx as ox

from core.geo import haversine_km
from risk.risk_engine import get_forecast_rainfall_sum_mm
from risk.upstream import compute_upstream_rain_index

NEGROS_GRAPH_PATH = Path(__file__).resolve().parents[1] / "data" / "negros_graph.graphml"
SAFETY_HUB_RADIUS_METERS = 5000
DEFAULT_SAFETY_WEIGHT = 2.0


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _load_negros_graph() -> nx.MultiDiGraph:
    if not NEGROS_GRAPH_PATH.exists():
        raise FileNotFoundError(
            "Negros road graph missing. Run scripts/load_negros_roads.py first."
        )

    return ox.load_graphml(NEGROS_GRAPH_PATH)


@lru_cache(maxsize=1)
def load_graph() -> nx.MultiDiGraph:
    return _load_negros_graph()


def nearest_node_id(graph: nx.Graph, lat: float, lng: float) -> int:
    try:
        nearest = ox.distance.nearest_nodes(graph, lng, lat)
        return int(nearest)
    except Exception:
        # Fallback when optional OSMnx/k-dtree deps (e.g., scikit-learn) are not installed.
        nearest = None
        nearest_distance = float("inf")
        for node_id, attrs in graph.nodes(data=True):
            node_lng = float(attrs.get("x", 0.0))
            node_lat = float(attrs.get("y", 0.0))
            distance = haversine_km(lat, lng, node_lat, node_lng)
            if distance < nearest_distance:
                nearest = node_id
                nearest_distance = distance
        if nearest is None:
            raise ValueError("No nodes found in road graph")
        return int(nearest)


def extract_local_graph(graph: nx.MultiDiGraph, origin: int, destination: int) -> nx.MultiDiGraph:
    base = nx.ego_graph(graph.to_undirected(), origin, radius=SAFETY_HUB_RADIUS_METERS, distance="length")
    if destination not in base:
        around_destination = nx.ego_graph(
            graph.to_undirected(),
            destination,
            radius=SAFETY_HUB_RADIUS_METERS,
            distance="length",
        )
        base = nx.compose(base, around_destination)

    if destination not in base:
        return graph.to_undirected()

    return graph.subgraph(base.nodes).copy()


def add_edge_hazard_scores(graph: nx.MultiDiGraph, rainfall_next_3h: float, upstream_risk_norm: float) -> None:
    for u, v, key, data in graph.edges(keys=True, data=True):
        if data.get("hazard_score") is not None:
            continue

        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        ux, uy = u_data.get("x", 0.0), u_data.get("y", 0.0)
        vx, vy = v_data.get("x", 0.0), v_data.get("y", 0.0)

        midpoint_lng = (ux + vx) / 2
        midpoint_lat = (uy + vy) / 2

        hazard = 0.0
        elevation = 9999
        try:
            from risk.risk_engine import get_elevation_meters

            elevation = get_elevation_meters(midpoint_lat, midpoint_lng, allow_remote_lookup=False)
        except Exception:
            elevation = 30

        if elevation < 20:
            hazard += 2

        from risk.risk_engine import distance_to_nearest_river_km

        distance_to_river_km = distance_to_nearest_river_km(midpoint_lat, midpoint_lng)
        if distance_to_river_km <= 0.25:
            hazard += 2
            hazard += (upstream_risk_norm / 100.0) * 4.0
        elif distance_to_river_km <= 0.75:
            hazard += (upstream_risk_norm / 100.0) * 2.0

        if rainfall_next_3h > 30:
            hazard += 1

        data["hazard_score"] = float(clamp(hazard, 0.0, 100.0))


def compute_safe_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    safety_weight: float = DEFAULT_SAFETY_WEIGHT,
    hours: int = 3,
    weather_mode: str = "live",
    reference_time: str | int | float | None = None,
    demo_rainfall: object | None = None,
) -> dict:
    safe_hours = int(clamp(hours, 1, 6))
    graph = load_graph()
    origin_node = nearest_node_id(graph, origin_lat, origin_lng)
    dest_node = nearest_node_id(graph, dest_lat, dest_lng)

    local_graph = extract_local_graph(graph, origin_node, dest_node)
    rainfall_sample = get_forecast_rainfall_sum_mm(
        origin_lat,
        origin_lng,
        safe_hours,
        weather_mode=weather_mode,
        reference_time=reference_time,
        demo_rainfall=demo_rainfall,
    )
    upstream_summary = compute_upstream_rain_index(
        lat=origin_lat,
        lng=origin_lng,
        horizon_hours=safe_hours,
        weather_mode=weather_mode,
        reference_time=reference_time,
        demo_rainfall=demo_rainfall,
    )

    add_edge_hazard_scores(
        local_graph,
        rainfall_sample,
        upstream_summary.get("upstream_rain_index_norm", 0.0),
    )

    def edge_cost(start, end, data):
        base_length = float(data.get("length", 1.0))
        hazard = float(data.get("hazard_score", 0.0))
        return base_length + (hazard * safety_weight)

    route_graph = local_graph
    try:
        path = nx.shortest_path(
            route_graph,
            source=origin_node,
            target=dest_node,
            weight=edge_cost,
        )
    except nx.NetworkXNoPath:
        # Fallback to full graph when ego-graph pruning omits a valid route.
        route_graph = graph.to_undirected()
        add_edge_hazard_scores(
            route_graph,
            rainfall_sample,
            upstream_summary.get("upstream_rain_index_norm", 0.0),
        )
        path = nx.shortest_path(
            route_graph,
            source=origin_node,
            target=dest_node,
            weight=edge_cost,
        )

    route = []
    total_distance = 0.0
    hazard_exposure = 0.0
    for node_id in path:
        node_attrs = route_graph.nodes[node_id]
        route.append(
            {
                "lat": node_attrs.get("y"),
                "lng": node_attrs.get("x"),
            }
        )

    for index in range(len(path) - 1):
        u = path[index]
        v = path[index + 1]
        edge_attrs = route_graph.get_edge_data(u, v)

        if len(edge_attrs) == 1:
            attrs = list(edge_attrs.values())[0]
        else:
            candidate = sorted(edge_attrs.values(), key=lambda item: edge_cost(u, v, item))[0]
            attrs = candidate

        total_distance += float(attrs.get("length", 0.0))
        hazard_exposure += float(attrs.get("hazard_score", 0.0))

    return {
        "route": route,
        "total_distance": round(total_distance, 3),
        "hazard_exposure": round(hazard_exposure, 3),
        "origin_node": origin_node,
        "destination_node": dest_node,
    }
