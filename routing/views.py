from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .routing_engine import compute_safe_route


@require_GET
def safe_route_api(request):
    try:
        origin_lat = float(request.GET.get("origin_lat"))
        origin_lng = float(request.GET.get("origin_lng"))
        dest_lat = float(request.GET.get("dest_lat"))
        dest_lng = float(request.GET.get("dest_lng"))
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "error": (
                    "origin_lat, origin_lng, dest_lat, and dest_lng are required numeric params"
                )
            },
            status=400,
        )

    mode = request.GET.get("mode", "safe").lower()
    if mode == "fast":
        safety_weight = 0.0
    elif mode == "safe":
        safety_weight = 2.0
    else:
        return JsonResponse({"error": "mode must be 'fast' or 'safe'"}, status=400)

    try:
        payload = compute_safe_route(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            safety_weight=safety_weight,
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse(payload)
