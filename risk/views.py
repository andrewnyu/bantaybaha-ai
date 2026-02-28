from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .risk_engine import estimate_flood_risk
from .risk_area import build_risk_area_payload


@require_GET
def risk_api(request):
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")
    hours = request.GET.get("hours", "3")

    if lat is None or lng is None:
        return JsonResponse({"error": "lat and lng are required"}, status=400)

    try:
        lat_f = float(lat)
        lng_f = float(lng)
        hours_i = int(hours)
    except ValueError:
        return JsonResponse({"error": "lat/lng must be float and hours must be int"}, status=400)

    payload = estimate_flood_risk(lat_f, lng_f, hours_i)
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
