from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.geo import haversine_km
from risk.risk_area import NEGROS_BOUNDS
from risk.risk_engine import distance_to_nearest_river_km

from .models import BacktestResult, BacktestRun


NEGROS_SLUG = "negros-island"
DEFAULT_HISTORICAL_RISK_THRESHOLD = 60
MAX_CELL_CELLS = 140
MAX_ROAD_EDGE_CELLS = 220
HISTORICAL_WEATHER_SOURCE = "historical_window_stub"
RIVER_SOURCE_POINTS = [
    (10.44, 122.86),
    (10.25, 122.94),
    (9.78, 122.66),
]


@dataclass
class BacktestRunResult:
    run: BacktestRun
    status: str
    runtime_ms: float
    nodes_processed: int
    edges_processed: int
    flooded_count: int
    top_results: list[dict[str, Any]] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)


class BacktestRateLimitError(RuntimeError):
    pass


class BacktestInputError(ValueError):
    pass


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _round2(value: float) -> float:
    return round(float(value), 2)


def _is_valid_area(area_slug: str) -> bool:
    return area_slug == NEGROS_SLUG


def _make_grid_points(max_points: int) -> list[tuple[float, float]]:
    bounded_points = max(20, max_points)
    rows = max(4, int(math.sqrt(bounded_points)))
    cols = max(6, int(math.sqrt(bounded_points) * 1.25))
    lat_span = NEGROS_BOUNDS["north"] - NEGROS_BOUNDS["south"]
    lng_span = NEGROS_BOUNDS["east"] - NEGROS_BOUNDS["west"]
    lat_step = lat_span / max(rows - 1, 1)
    lng_step = lng_span / max(cols - 1, 1)

    points: list[tuple[float, float]] = []
    for row in range(rows):
        lat = NEGROS_BOUNDS["south"] + (lat_step * row)
        for col in range(cols):
            lng = NEGROS_BOUNDS["west"] + (lng_step * col)
            points.append((_round2(lat), _round2(lng)))
            if len(points) >= bounded_points:
                return points
    return points


def _sample_in_chunks(points: list[Any], max_count: int) -> list[Any]:
    if len(points) <= max_count:
        return points
    step = max(1, math.ceil(len(points) / max_count))
    return points[::step][:max_count]


def _simulate_downstream_rain_signature(lat: float, lng: float, weather_summary: dict[str, Any]) -> float:
    river_point = min((haversine_km(lat, lng, source_lat, source_lng) for source_lat, source_lng in RIVER_SOURCE_POINTS))
    decay = max(0.2, 1.0 - (river_point / 160.0))
    peak_rain = weather_summary["max_rainfall_mm"]
    return _clamp(peak_rain * 1.25 * decay, 0.0, 100.0)


def _historical_hourly_series(start_dt: datetime, end_dt: datetime, include_weather: bool = True) -> list[dict[str, Any]]:
    if start_dt >= end_dt:
        raise BacktestInputError("Start datetime must be before end datetime.")

    total_hours = max(1, int((end_dt - start_dt).total_seconds() // 3600) + 1)
    samples: list[dict[str, Any]] = []

    # deterministic historical-like wave: event-shaped curve + diurnal variation.
    for idx in range(total_hours):
        sample_ts = start_dt + timedelta(hours=idx)
        wave = (idx / max(total_hours, 1)) * math.pi
        hour_phase = (sample_ts.hour + sample_ts.minute / 60.0) / 24.0 * 2 * math.pi
        base_rain = 12.0 + 14.0 * (math.sin(wave) + 1) / 2
        diurnal = 5.0 + 2.0 * math.sin(hour_phase)
        hourly_rain = round(base_rain + diurnal, 2) if include_weather else 0.0

        if hourly_rain < 0:
            hourly_rain = 0.0

        samples.append({"timestamp": sample_ts, "rainfall_mm": hourly_rain})

    return samples


def _build_historical_weather(start_dt: datetime, end_dt: datetime, include_weather: bool = True) -> dict[str, Any]:
    # Backtest pipeline runs off historical window values (not live forecast API).
    # TODO: replace with real historical weather source when available (batch external call).
    samples = _historical_hourly_series(start_dt, end_dt, include_weather=include_weather)
    rain_values = [item["rainfall_mm"] for item in samples]
    avg_rain = sum(rain_values) / len(rain_values) if rain_values else 0.0
    max_rain = max(rain_values) if rain_values else 0.0

    return {
        "samples": samples,
        "avg_rainfall_mm": _round2(avg_rain),
        "max_rainfall_mm": _round2(max_rain),
        "source": HISTORICAL_WEATHER_SOURCE,
    }


def _risk_score_for_point(
    lat: float,
    lng: float,
    weather_summary: dict[str, Any],
    sources: dict[str, bool],
) -> tuple[float, dict[str, Any]]:
    weather_signal = weather_summary["avg_rainfall_mm"] if sources["weather"] else 0.0
    elevation_proxy = 22.0 + 9.0 * math.sin(lat * 2.3) + 7.0 * math.cos(lng * 2.7)
    low_elev_penalty = 14.0 if elevation_proxy >= 20 else 24.0

    if sources["rivers"]:
        river_distance = distance_to_nearest_river_km(lat, lng)
        river_signal = _clamp(70.0 - (river_distance * 4.0), 0.0, 50.0)
    else:
        river_signal = 0.0
        river_distance = None

    downstream_signal = _simulate_downstream_rain_signature(
        lat,
        lng,
        weather_summary,
    )

    score = (
        (weather_signal * 1.15)
        + (downstream_signal * 0.75)
        + river_signal
        + (low_elev_penalty if elevation_proxy < 25 else 4.0)
        + (8.0 if sources["roads"] else 0.0)
    )
    if not sources["weather"] and not sources["rivers"]:
        score *= 0.35

    return _clamp(score), {
        "weather_signal": weather_signal,
        "river_distance_km": river_distance,
        "downstream_signal": downstream_signal,
        "low_elevation_signal": low_elev_penalty if elevation_proxy < 25 else 4.0,
        "elevation_proxy": _round2(elevation_proxy),
    }


def _build_cell_payload(
    weather_summary: dict[str, Any],
    sources: dict[str, bool],
) -> list[dict[str, Any]]:
    points = _sample_in_chunks(_make_grid_points(MAX_CELL_CELLS), MAX_CELL_CELLS)
    samples = weather_summary["samples"]
    payload: list[dict[str, Any]] = []

    for idx, (lat, lng) in enumerate(points):
        timestamp = samples[idx % len(samples)]["timestamp"]
        risk_score, details = _risk_score_for_point(lat, lng, weather_summary, sources)
        payload.append(
            {
                "object_type": BacktestResult.ObjectType.CELL,
                "object_id": f"cell-{idx+1}",
                "risk_score": risk_score,
                "timestamp": timestamp,
                "extra_json": {
                    "lat": lat,
                    "lng": lng,
                    **details,
                },
            }
        )

    return payload


def _build_road_payload(
    start_dt: datetime,
    weather_summary: dict[str, Any],
    sources: dict[str, bool],
) -> tuple[list[dict[str, Any]], int, int]:
    try:
        from routing.routing_engine import load_graph
    except Exception as exc:  # pragma: no cover - exercised only if route deps unavailable
        raise RuntimeError(f"Road engine unavailable: {exc}") from exc

    graph = load_graph()
    nodes_processed = graph.number_of_nodes()
    edges = list(graph.edges(keys=True, data=True))
    selected_edges = _sample_in_chunks(edges, MAX_ROAD_EDGE_CELLS)
    payload: list[dict[str, Any]] = []

    for idx, (u, v, _key, _edge_data) in enumerate(selected_edges):
        u_attrs = graph.nodes[u]
        v_attrs = graph.nodes[v]
        u_lat = float(u_attrs.get("y", 0.0))
        u_lng = float(u_attrs.get("x", 0.0))
        v_lat = float(v_attrs.get("y", 0.0))
        v_lng = float(v_attrs.get("x", 0.0))
        mid_lat = _round2((u_lat + v_lat) / 2)
        mid_lng = _round2((u_lng + v_lng) / 2)
        score, details = _risk_score_for_point(mid_lat, mid_lng, weather_summary, sources)
        payload.append(
            {
                "object_type": BacktestResult.ObjectType.EDGE,
                "object_id": f"edge-{u}-{v}-{idx}",
                "risk_score": score,
                "timestamp": start_dt + timedelta(hours=idx % max(len(weather_summary["samples"]), 1)),
                "extra_json": {
                    "lat": mid_lat,
                    "lng": mid_lng,
                    "source_node": str(u),
                    "target_node": str(v),
                    **details,
                },
            }
        )

    return payload, nodes_processed, len(payload)


def run_backtest(
    area_slug: str,
    start_dt: datetime,
    end_dt: datetime,
    sources: dict[str, bool],
) -> BacktestRunResult:
    if not _is_valid_area(area_slug):
        raise BacktestInputError("Only Negros Island is available in the MVP testing scope.")

    if not any(sources.values()):
        raise BacktestInputError("Select at least one source.")

    running_window = timezone.now() - timedelta(minutes=2)
    if BacktestRun.objects.filter(status=BacktestRun.Status.RUNNING, created_at__gte=running_window).exists():
        raise BacktestRateLimitError("Another testing run is already running in the last 2 minutes.")

    run = BacktestRun.objects.create(
        area_slug=area_slug,
        start_dt=start_dt,
        end_dt=end_dt,
        status=BacktestRun.Status.RUNNING,
        notes={"sources": sources},
    )

    started = time.perf_counter()
    status = BacktestRun.Status.RUNNING
    nodes_processed = 0
    edges_processed = 0
    payload_rows: list[dict[str, Any]] = []
    notes: dict[str, Any] = {
        "requested_sources": sources,
    }
    weather_summary: dict[str, Any] = {
        "source": "mock",
        "samples": [],
        "avg_rainfall_mm": 0.0,
        "max_rainfall_mm": 0.0,
    }

    try:
        weather_summary = _build_historical_weather(
            start_dt=start_dt,
            end_dt=end_dt,
            include_weather=sources["weather"],
        )
        notes["weather_summary"] = {
            "source": weather_summary["source"],
            "samples": weather_summary["samples"],
            "avg_rainfall_mm": weather_summary["avg_rainfall_mm"],
            "max_rainfall_mm": weather_summary["max_rainfall_mm"],
        }

        payload_rows.extend(_build_cell_payload(weather_summary=weather_summary, sources=sources))
        if sources["roads"]:
            try:
                road_rows, nodes_processed, edges_processed = _build_road_payload(
                    start_dt=start_dt,
                    weather_summary=weather_summary,
                    sources=sources,
                )
                payload_rows.extend(road_rows)
            except Exception as exc:
                notes["road_error"] = str(exc)
                nodes_processed = 0
                edges_processed = 0

        status = BacktestRun.Status.COMPLETED
    except Exception as exc:
        status = BacktestRun.Status.FAILED
        notes = {
            **notes,
            "error": str(exc),
        }
    finally:
        runtime_ms = _round2((time.perf_counter() - started) * 1000.0)
        run.status = status
        run.runtime_ms = runtime_ms
        run.notes = {
            **run.notes,
            **notes,
            "weather_samples": weather_summary.get("samples", []),
        }
        run.save(update_fields=["status", "runtime_ms", "notes"])

        if payload_rows and status == BacktestRun.Status.COMPLETED:
            result_models = [
                BacktestResult(
                    run=run,
                    object_type=row["object_type"],
                    object_id=row["object_id"],
                    risk_score=row["risk_score"],
                    timestamp=row["timestamp"],
                    extra_json=row["extra_json"],
                )
                for row in payload_rows
            ]
            with transaction.atomic():
                BacktestResult.objects.bulk_create(result_models)

    top_results = sorted(payload_rows, key=lambda row: row["risk_score"], reverse=True)[:20]
    flooded_count = sum(1 for row in payload_rows if row["risk_score"] >= DEFAULT_HISTORICAL_RISK_THRESHOLD)

    return BacktestRunResult(
        run=run,
        status=run.status,
        runtime_ms=runtime_ms,
        nodes_processed=nodes_processed,
        edges_processed=edges_processed,
        flooded_count=flooded_count,
        top_results=top_results,
        notes=run.notes,
    )
