from .geo import haversine_km
from .models import EvacuationCenter


def nearest_evacuation_centers(
    lat: float,
    lng: float,
    limit: int | None = 3,
    max_radius_km: float = 200.0,
    radius_step_km: float = 10.0,
) -> list[dict]:
    candidates = []
    for center in EvacuationCenter.objects.all():
        distance_km = haversine_km(lat, lng, center.latitude, center.longitude)
        candidates.append(
            {
                "name": center.name,
                "latitude": center.latitude,
                "longitude": center.longitude,
                "capacity": center.capacity,
                "distance_km": round(distance_km, 3),
            }
        )

    candidates.sort(key=lambda item: item["distance_km"])

    if not candidates:
        return []

    search_radius = radius_step_km
    while search_radius <= max_radius_km:
        options = [center for center in candidates if center["distance_km"] <= search_radius]
        if options:
            if limit is None:
                return options
            return options[:limit]
        search_radius += radius_step_km

    return []
