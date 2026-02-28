import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import LineString, MultiLineString

from core.geo import haversine_km
from risk.risk_engine import get_elevation_meters

BASE_DIR = Path(__file__).resolve().parents[1]
NEGROS_PLACE = "Negros Island, Philippines"
RIVER_SOURCE_PATH = BASE_DIR / "data" / "negros_rivers.geojson"
RIVER_GRAPH_PATH = BASE_DIR / "data" / "negros_river_graph.gpickle"
SAMPLE_POINTS_PATH = BASE_DIR / "data" / "river_sample_points.json"


def _load_river_geometries() -> gpd.GeoDataFrame:
    if RIVER_SOURCE_PATH.exists():
        return gpd.read_file(RIVER_SOURCE_PATH)

    ox.settings.log_console = False
    print("No local river file found. Pulling waterways from OSM...")
    return ox.geometries_from_place(
        NEGROS_PLACE,
        tags={"waterway": ["river", "stream", "canal"]},
    )


def _node_id(lat: float, lng: float) -> str:
    return f"{round(float(lat), 6)},{round(float(lng), 6)}"


def build_directed_river_graph() -> nx.DiGraph:
    waterways = _load_river_geometries()
    g = nx.DiGraph()

    if waterways.empty:
        print("No river features available for Negros")
        return g

    for geometry in waterways.geometry:
        if geometry is None or geometry.is_empty:
            continue

        geometries = []
        if isinstance(geometry, LineString):
            geometries.append(geometry)
        elif isinstance(geometry, MultiLineString):
            geometries.extend(list(geometry.geoms))
        else:
            continue

        for line in geometries:
            coords = list(line.coords)
            if len(coords) < 2:
                continue

            for start_idx in range(len(coords) - 1):
                start_lng, start_lat = coords[start_idx]
                end_lng, end_lat = coords[start_idx + 1]

                start_node = _node_id(start_lat, start_lng)
                end_node = _node_id(end_lat, end_lng)

                g.add_node(start_node, lat=start_lat, lng=start_lng)
                g.add_node(end_node, lat=end_lat, lng=end_lng)

                start_elev = get_elevation_meters(start_lat, start_lng, allow_remote_lookup=False)
                end_elev = get_elevation_meters(end_lat, end_lng, allow_remote_lookup=False)

                if start_elev > end_elev:
                    u, v = start_node, end_node
                elif end_elev > start_elev:
                    u, v = end_node, start_node
                elif start_node <= end_node:
                    u, v = start_node, end_node
                else:
                    u, v = end_node, start_node

                length_m = haversine_km(start_lat, start_lng, end_lat, end_lng) * 1000
                g.add_edge(
                    u,
                    v,
                    length_m=round(float(length_m), 3),
                    source_segment="osm",
                    source_node=u,
                    target_node=v,
                )

    return g


def build_and_store_samples(graph: nx.DiGraph) -> list[dict]:
    sample_points = []
    for node_id, attrs in graph.nodes(data=True):
        sample_points.append(
            {
                "id": str(node_id),
                "lat": attrs.get("lat"),
                "lng": attrs.get("lng"),
            }
        )

    SAMPLE_POINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_POINTS_PATH.write_text(json.dumps({"points": sample_points}, indent=2))
    return sample_points


def main() -> None:
    RIVER_GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Building directed river graph from OSM waterways ...")
    graph = build_directed_river_graph()
    if graph.number_of_nodes() == 0:
        print("River graph is empty. Check data source.")
        return

    nx.write_gpickle(graph, RIVER_GRAPH_PATH)
    print(f"Wrote {RIVER_GRAPH_PATH}")

    points = build_and_store_samples(graph)
    print(f"Wrote {len(points)} river sample points to {SAMPLE_POINTS_PATH}")


if __name__ == "__main__":
    main()
