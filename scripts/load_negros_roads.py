from pathlib import Path

import osmnx as ox

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
NEGROS_PLACE = "Negros Island, Philippines"
GRAPH_PATH = DATA_DIR / "negros_graph.graphml"
RIVER_PATH = DATA_DIR / "negros_rivers.geojson"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_and_save_road_graph() -> None:
    print("Downloading Negros Island drivable road network from OSM...")
    graph = ox.graph_from_place(NEGROS_PLACE, network_type="drive", simplify=True)
    ox.save_graphml(graph, path=GRAPH_PATH)
    print(f"Saved road graph to {GRAPH_PATH}")


def load_and_save_rivers() -> None:
    print("Downloading river/network waterways from OSM...")
    waterways = ox.geometries_from_place(
        NEGROS_PLACE, tags={"waterway": ["river", "stream", "canal"]}
    )
    if waterways.empty:
        print("No waterways found, skipping river output")
        return

    waterways = waterways[waterways.geometry.notna()]
    waterways.to_file(RIVER_PATH, driver="GeoJSON")
    print(f"Saved river network to {RIVER_PATH}")


def main() -> None:
    ox.settings.log_console = False
    ensure_data_dir()
    load_and_save_road_graph()
    load_and_save_rivers()


if __name__ == "__main__":
    main()
