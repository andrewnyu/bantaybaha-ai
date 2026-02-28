import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from weather.client import parse_demo_rainfall_values

from .tool_router import run_tool_router


def _normalize_weather_mode(raw_mode: str | None) -> str:
    normalized = (raw_mode or "live").strip().lower()
    if normalized in {"realtime", "current", "now"}:
        return "live"
    if normalized == "demo":
        return "demo"
    if normalized in {"historical", "history", "past"}:
        return "historical"
    return normalized


def _normalize_hours(raw_hours: object | None, default_hours: int = 3) -> int:
    try:
        value = int(raw_hours)
    except (TypeError, ValueError):
        return default_hours

    return max(1, min(6, value))


@csrf_exempt
@require_POST
def chat_api(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    message = payload.get("message", "").strip()
    if not message:
        return JsonResponse({"error": "message is required"}, status=400)

    try:
        lat = float(payload.get("lat", 14.5995))
        lng = float(payload.get("lng", 120.9842))
        dest_lat = payload.get("dest_lat")
        dest_lng = payload.get("dest_lng")
        dest_lat = float(dest_lat) if dest_lat is not None else None
        dest_lng = float(dest_lng) if dest_lng is not None else None
        forecast_hours = _normalize_hours(payload.get("hours", 3), 3)
        weather_mode = _normalize_weather_mode(payload.get("weather_mode"))
        demo_rainfall_raw = payload.get("demo_rainfall")
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "lat/lng/dest_lat/dest_lng must be numeric when provided"},
            status=400,
        )

    demo_rainfall = None
    if weather_mode == "demo":
        try:
            demo_rainfall = parse_demo_rainfall_values(demo_rainfall_raw)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    tool_calls = payload.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, list):
        return JsonResponse({"error": "tool_calls must be an array"}, status=400)
    chat_history = payload.get("chat_history")
    if chat_history is not None and not isinstance(chat_history, list):
        return JsonResponse({"error": "chat_history must be an array"}, status=400)

    result = run_tool_router(
        message=message,
        lat=lat,
        lng=lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        hours=forecast_hours,
        tool_calls=tool_calls,
        chat_history=chat_history,
        weather_mode=weather_mode if weather_mode in {"live", "demo"} else "live",
        demo_rainfall=demo_rainfall,
    )
    return JsonResponse(result)
