from django.http import JsonResponse
from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .services import nearest_evacuation_centers


def index(request):
    return render(request, "index.html", {
        "has_openai_key": bool(settings.OPENAI_API_KEY),
    })


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
