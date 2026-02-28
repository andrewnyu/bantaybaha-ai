from django.http import JsonResponse
from django.views.decorators.http import require_GET
from weather.client import parse_reference_time

from .routing_engine import compute_safe_route


def _normalize_weather_mode(raw_mode: str | None) -> str:
    normalized = (raw_mode or "live").strip().lower()
    if normalized in {"realtime", "current", "now"}:
        return "live"
    if normalized in {"historical", "history", "past"}:
        return "historical"
    return normalized


@require_GET
def safe_route_api(request):
    try:
        origin_lat = float(request.GET.get("origin_lat"))
        origin_lng = float(request.GET.get("origin_lng"))
        dest_lat = float(request.GET.get("dest_lat"))
        dest_lng = float(request.GET.get("dest_lng"))
        hours = int(request.GET.get("hours", "3"))
        weather_mode = _normalize_weather_mode(request.GET.get("weather_mode"))
        reference_time = request.GET.get("reference_time")
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "error": (
                    "origin_lat, origin_lng, dest_lat, and dest_lng are required numeric params"
                )
            },
            status=400,
        )

    if weather_mode == "historical":
        if reference_time is None:
            return JsonResponse(
                {"error": "reference_time is required when weather_mode=historical"},
                status=400,
            )
        try:
            reference_epoch = parse_reference_time(reference_time)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
    elif weather_mode != "live":
        return JsonResponse({"error": "weather_mode must be 'live' or 'historical'"}, status=400)
    else:
        reference_epoch = None

    mode = request.GET.get("mode", "safest").lower()
    if mode in {"fast", "fastest"}:
        safety_weight = 0.0
    elif mode in {"safe", "safest"}:
        safety_weight = 2.0
    else:
        return JsonResponse({"error": "mode must be 'fast', 'fastest', 'safe', or 'safest'"}, status=400)

    try:
        payload = compute_safe_route(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            safety_weight=safety_weight,
            hours=hours,
            weather_mode=weather_mode,
            reference_time=reference_epoch,
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse(payload)
