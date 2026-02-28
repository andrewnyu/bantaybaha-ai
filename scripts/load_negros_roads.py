from pathlib import Path

import osmnx as ox

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
NEGROS_PLACE = "Negros Island, Philippines"
GRAPH_PATH = DATA_DIR / "negros_graph.graphml"
RIVER_PATH = DATA_DIR / "negros_rivers.geojson"


def _query_waterways(place_name: str):
    """Compatibility wrapper for OSMnx API differences."""
    fetcher = getattr(ox, "geometries_from_place", None) or getattr(
        ox, "features_from_place", None
    )
    if fetcher is None:
        raise AttributeError("OSMnx does not expose geometries/features query function.")
    return fetcher(place_name, tags={"waterway": ["river", "stream", "canal"]})


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_and_save_road_graph() -> None:
    print("Downloading Negros Island drivable road network from OSM...")
    graph = ox.graph_from_place(NEGROS_PLACE, network_type="drive", simplify=True)

    # OSMnx save API differs across versions.
    # Use positional argument for broad compatibility.
    ox.save_graphml(graph, str(GRAPH_PATH))
    print(f"Saved road graph to {GRAPH_PATH}")


def load_and_save_rivers() -> None:
    print("Downloading river/network waterways from OSM...")
    try:
        waterways = _query_waterways(NEGROS_PLACE)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"Skipping river download (network/data unavailable): {type(exc).__name__}")
        return

    if waterways.empty:
        print("No waterways found, skipping river output")
        return

    waterways = waterways[waterways.geometry.notna()]
    if waterways.empty:
        print("No valid river geometries found, skipping river output")
        return

    waterways.to_file(RIVER_PATH, driver="GeoJSON")
    print(f"Saved river network to {RIVER_PATH}")


def main() -> None:
    ox.settings.log_console = False
    ensure_data_dir()
    load_and_save_road_graph()
    load_and_save_rivers()


if __name__ == "__main__":
    main()
