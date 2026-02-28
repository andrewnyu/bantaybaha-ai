from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .risk_engine import estimate_flood_risk


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
