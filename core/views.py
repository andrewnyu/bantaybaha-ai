from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.conf import settings

from .services import nearest_evacuation_centers


def index(request):
    openai_key = str(getattr(settings, "OPENAI_API_KEY", "")).strip()
    openai_configured = bool(openai_key) and openai_key != "your_key_here"
    return render(request, "index.html", {"openai_configured": openai_configured})


@require_GET
def nearest_evac_centers_api(request):
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")

    if lat is None or lng is None:
        return JsonResponse({"error": "lat and lng are required"}, status=400)

    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except ValueError:
        return JsonResponse({"error": "lat and lng must be numeric"}, status=400)

    centers = nearest_evacuation_centers(lat_f, lng_f, limit=3)
    return JsonResponse({"centers": centers})
