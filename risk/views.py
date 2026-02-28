from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .risk_engine import estimate_flood_risk
from .risk_area import build_risk_area_payload
from weather.client import parse_demo_rainfall_values, parse_demo_upstream_rainfall, parse_reference_time


def _normalize_weather_mode(raw_mode: str | None) -> str:
    normalized = (raw_mode or "live").strip().lower()
    if normalized in {"realtime", "current", "now"}:
        return "live"
    if normalized in {"historical", "history", "past"}:
        return "historical"
    if normalized == "demo":
        return "demo"
    return normalized


@require_GET
def risk_api(request):
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")
    hours = request.GET.get("hours", "3")
    weather_mode = _normalize_weather_mode(request.GET.get("weather_mode"))
    reference_time = request.GET.get("reference_time")
    demo_rainfall_raw = request.GET.get("demo_rainfall")
    demo_rainfall: list[float] | None = None
    demo_upstream_rainfall: dict[str, list[float]] = {}

    if lat is None or lng is None:
        return JsonResponse({"error": "lat and lng are required"}, status=400)

    try:
        lat_f = float(lat)
        lng_f = float(lng)
        hours_i = int(hours)
    except ValueError:
        return JsonResponse({"error": "lat/lng must be float and hours must be int"}, status=400)

    reference_epoch = None
    if weather_mode == "historical":
        if reference_time is None:
            return JsonResponse(
                {
                    "error": "reference_time is required when weather_mode=historical"
                },
                status=400,
            )
        try:
            reference_epoch = parse_reference_time(reference_time)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
    elif weather_mode == "demo":
        try:
            demo_rainfall = parse_demo_rainfall_values(demo_rainfall_raw)
            demo_upstream_rainfall = parse_demo_upstream_rainfall(
                request.GET.get("demo_upstream_rainfall")
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    if weather_mode not in {"live", "historical", "demo"}:
        return JsonResponse(
            {
                "error": "weather_mode must be 'live', 'historical', or 'demo'"
            },
            status=400,
        )

    payload = estimate_flood_risk(
        lat_f,
        lng_f,
        hours_i,
        weather_mode=weather_mode,
        reference_time=reference_epoch,
        demo_rainfall=demo_rainfall,
        demo_upstream_rainfall=demo_upstream_rainfall,
    )
    return JsonResponse(payload)


def _parse_bool_param(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


@require_GET
def risk_area_api(request):
    hours = request.GET.get("hours", "3")
    severity = request.GET.get("severity", "high")
    max_points = request.GET.get("max_points", "140")
    include_rivers = request.GET.get("include_rivers", "true")
    include_roads = request.GET.get("include_roads", "true")

    try:
        hours_i = int(hours)
        max_points_i = int(max_points)
    except ValueError:
        return JsonResponse(
            {
                "error": "hours and max_points must be integers",
            },
            status=400,
        )

    payload = build_risk_area_payload(
        hours=hours_i,
        severity=severity,
        max_points=max_points_i,
        include_rivers=_parse_bool_param(include_rivers, default=True),
        include_roads=_parse_bool_param(include_roads, default=True),
    )
    return JsonResponse(payload)
