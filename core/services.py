from .geo import haversine_km
from .models import EvacuationCenter


def nearest_evacuation_centers(lat: float, lng: float, limit: int = 3) -> list[dict]:
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
    return candidates[:limit]
