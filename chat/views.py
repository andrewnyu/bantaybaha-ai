import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .tool_router import run_tool_router


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
        language = payload.get("language", "en")
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "lat/lng/dest_lat/dest_lng must be numeric when provided"},
            status=400,
        )

    tool_calls = payload.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, list):
        return JsonResponse({"error": "tool_calls must be an array"}, status=400)

    result = run_tool_router(
        message=message,
        lat=lat,
        lng=lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        language=language,
        tool_calls=tool_calls,
    )
    return JsonResponse(result)
