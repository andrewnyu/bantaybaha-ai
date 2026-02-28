import re
from dataclasses import dataclass

from core.services import nearest_evacuation_centers
from risk.risk_engine import estimate_flood_risk
from routing.routing_engine import compute_safe_route

DEFAULT_LAT = 14.5995
DEFAULT_LNG = 120.9842
DEFAULT_DEST_LAT = 14.6396
DEFAULT_DEST_LNG = 121.098


@dataclass
class ChatContext:
    lat: float = DEFAULT_LAT
    lng: float = DEFAULT_LNG
    dest_lat: float = DEFAULT_DEST_LAT
    dest_lng: float = DEFAULT_DEST_LNG


def parse_coordinate_pairs(message: str) -> list[tuple[float, float]]:
    matches = re.findall(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", message)
    return [(float(lat), float(lng)) for lat, lng in matches]


def detect_intents(message: str) -> dict:
    lower = message.lower()
    return {
        "risk": "risk" in lower,
        "evac": ("evac" in lower) or ("where" in lower),
        "route": ("route" in lower) or ("go" in lower),
    }


def run_chat_agent(message: str, context: ChatContext) -> dict:
    intents = detect_intents(message)
    coordinate_pairs = parse_coordinate_pairs(message)

    if len(coordinate_pairs) >= 1:
        context.lat, context.lng = coordinate_pairs[0]
    if len(coordinate_pairs) >= 2:
        context.dest_lat, context.dest_lng = coordinate_pairs[1]

    actions_taken = []
    replies = []

    if intents["risk"]:
        risk_payload = estimate_flood_risk(context.lat, context.lng, hours=3)
        actions_taken.append("risk_check")
        replies.append(
            f"Estimated flood risk is {risk_payload['risk_level']} ({risk_payload['risk_score']}/100)."
        )

    nearest_centers = []
    if intents["evac"]:
        nearest_centers = nearest_evacuation_centers(context.lat, context.lng, limit=3)
        actions_taken.append("evac_lookup")
        if nearest_centers:
            summary = ", ".join(
                [f"{item['name']} ({item['distance_km']} km)" for item in nearest_centers]
            )
            replies.append(f"Nearest evacuation centers: {summary}.")
        else:
            replies.append("No evacuation centers available yet.")

    if intents["route"]:
        if nearest_centers:
            context.dest_lat = nearest_centers[0]["latitude"]
            context.dest_lng = nearest_centers[0]["longitude"]

        route_payload = compute_safe_route(
            origin_lat=context.lat,
            origin_lng=context.lng,
            dest_lat=context.dest_lat,
            dest_lng=context.dest_lng,
            safety_weight=2.0,
        )
        actions_taken.append("safe_route")
        replies.append(
            "Suggested safer route is "
            f"{route_payload['total_distance']} km with "
            f"hazard exposure {route_payload['hazard_exposure']}."
        )

    if not actions_taken:
        replies.append(
            "I can check flood risk, find nearby evacuation centers, or compute a safer route. "
            "Try including 'risk', 'evac', or 'route' in your message."
        )

    return {
        "reply": " ".join(replies),
        "actions_taken": actions_taken,
    }
