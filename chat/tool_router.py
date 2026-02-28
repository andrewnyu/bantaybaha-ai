import json
import re
from typing import Any

from core.services import nearest_evacuation_centers
from risk.risk_engine import estimate_flood_risk
from risk.upstream import compute_upstream_rain_index
from routing.routing_engine import compute_safe_route


def parse_coordinate_pairs(message: str) -> list[tuple[float, float]]:
    matches = re.findall(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", message)
    return [(float(lat), float(lng)) for lat, lng in matches]


def tool_get_risk(lat: float, lng: float, hours: int = 3) -> dict:
    payload = estimate_flood_risk(lat=lat, lng=lng, hours=hours)
    return {
        "tool": "tool_get_risk",
        "result": payload,
    }


def tool_get_upstream_summary(lat: float, lng: float, hours: int = 3) -> dict:
    payload = compute_upstream_rain_index(lat=lat, lng=lng, horizon_hours=hours)
    return {
        "tool": "tool_get_upstream_summary",
        "result": payload,
    }


def tool_get_evac_centers(lat: float, lng: float, limit: int = 3) -> dict:
    payload = nearest_evacuation_centers(lat=lat, lng=lng, limit=limit)
    return {
        "tool": "tool_get_evac_centers",
        "result": payload,
    }


def _resolve_destination_from_centers(
    centers: list[dict],
    payload: dict | None,
) -> tuple[float, float] | None:
    if centers:
        chosen = centers[0]
        return float(chosen["latitude"]), float(chosen["longitude"])

    if isinstance(payload, dict) and payload.get("dominant_upstream_points"):
        first = payload["dominant_upstream_points"][0]
        return float(first["lat"]), float(first["lng"])

    return None


def tool_get_safe_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    mode: str = "safest",
) -> dict:
    safety_weight = 2.0 if mode in {"safe", "safest"} else 0.0
    payload = compute_safe_route(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        safety_weight=safety_weight,
    )
    payload["mode"] = "safest" if safety_weight > 0 else "fastest"
    return {
        "tool": "tool_get_safe_route",
        "result": payload,
    }


def _build_tool_plan(message: str, default_hours: int, need_route: bool) -> list[dict]:
    lower = message.lower()
    include_risk = "risk" in lower or "rain" in lower or "typhoon" in lower or "weather" in lower
    include_evac = "evac" in lower or "where" in lower or "evacuate" in lower
    include_route = "route" in lower or "go" in lower or need_route
    include_upstream = "upstream" in lower or "downstream" in lower

    if "fastest" in lower:
        route_mode = "fastest"
    elif "safe" in lower:
        route_mode = "safest"
    else:
        route_mode = "safest"

    if not (include_risk or include_evac or include_route or include_upstream):
        include_risk = True

    plan = []
    if include_risk:
        plan.append({"tool": "tool_get_risk", "arguments": {"hours": default_hours}})
    if include_upstream:
        plan.append({"tool": "tool_get_upstream_summary", "arguments": {"hours": default_hours}})
    if include_evac:
        plan.append({"tool": "tool_get_evac_centers", "arguments": {}})
    if include_route:
        plan.append({"tool": "tool_get_safe_route", "arguments": {"mode": route_mode}})

    return plan


def _plan_actions(payload: list[dict]) -> list[str]:
    return [item.get("tool") for item in payload]


def _normalize_language(language: str | None) -> str:
    language = (language or "en").lower().strip()
    return language if language in {"en", "tl", "ilo"} else "en"


def _build_conversational_reply(tool_results: dict[str, Any], language: str) -> str:
    lang = _normalize_language(language)

    if lang == "tl":
        risk_label = "Panganib"
        upstream_label = "Bagay sa tubig-ulan sa itaas na bahagi"
        evac_label = "Pinakamalapit na evacuation center"
        route_label = "Ruta"
        no_data = "Naka-assemble ako ng sagot, pero mukhang kulang ang data para sa query na ito."
        default_action = (
            "Maaari kong kunin ang risk, upstream rainfall signals, "
            "evacuation centers, at mga ruta. Subukan ang: "
            "\"check risk\", \"find nearest evacuation center\", o \"safe route to nearest evacuation center\"."
        )
        units_km = "km"
    elif lang == "ilo":
        risk_label = "Peligro"
        upstream_label = "Pagsulod sang ulan sa pinutikan"
        evac_label = "Pinakadaku nga evacuation center nga duul"
        route_label = "Ruta"
        no_data = "Nakuha ko ang resulta pero daw kulang ang data para sa imo pangabay."
        default_action = (
            "Maka-check ako sang risk, upstream signals, evacuation centers, kag mga ruta. "
            "Pwede mo i-sabi: \"check risk\", \"find nearest evacuation center\", o \"safe route to nearest evacuation center\"."
        )
        units_km = "km"
    else:
        risk_label = "Flood risk"
        upstream_label = "Upstream rainfall signal"
        evac_label = "Nearest evacuation center"
        route_label = "Route"
        no_data = "I did everything I can, but this query did not return enough data."
        default_action = (
            "I can check flood risk, upstream signals, evacuation centers, and route options. "
            'Try: "check risk", "find nearest evacuation center", or "safe route to nearest evacuation center".'
        )
        units_km = "km"

    if not tool_results:
        return default_action

    lines = []
    if "risk" in tool_results:
        risk_payload = tool_results["risk"]
        lines.append(
            f"{risk_label}: {risk_payload['risk_level']} ({risk_payload['risk_score']}/100)"
        )
        explanations = risk_payload.get("explanation")
        if explanations:
            lines.append("Signals: " + ", ".join(explanations))

    if "upstream" in tool_results:
        up = tool_results["upstream"]
        peak = up.get("expected_peak_in_hours")
        peak_text = f"~{peak}h" if peak is not None else "n/a"
        lines.append(
            f"{upstream_label}: {up['upstream_rain_index']} (normalized {up['upstream_rain_index_norm']}), "
            f"possible impact in {peak_text}."
        )

    if "evac" in tool_results:
        if tool_results["evac"]:
            first = tool_results["evac"][0]
            lines.append(
                f"{evac_label}: {first['name']} - {first['distance_km']} {units_km} away."
            )

    if "route" in tool_results:
        route = tool_results["route"]
        lines.append(
            f"{route_label}: {route['total_distance']} {units_km}, "
            f"hazard exposure {route['hazard_exposure']}."
        )

    if not lines:
        return no_data

    return " ".join(lines)


def run_tool_router(
    message: str,
    lat: float,
    lng: float,
    dest_lat: float | None = None,
    dest_lng: float | None = None,
    language: str | None = "en",
    tool_calls: list[dict] | None = None,
) -> dict:
    lat_lng_pairs = parse_coordinate_pairs(message)
    if lat_lng_pairs:
        lat, lng = lat_lng_pairs[0]
        if len(lat_lng_pairs) >= 2:
            dest_lat, dest_lng = lat_lng_pairs[1]

    default_hours = 3
    requested_hours = 3
    if tool_calls is None:
        tool_calls = _build_tool_plan(message, requested_hours, dest_lat is not None and dest_lng is not None)

    tool_outputs = []
    tool_results: dict[str, Any] = {}

    evac_centers = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("tool")
        args = tool_call.get("arguments", {}) if isinstance(tool_call, dict) else {}

        if tool_name == "tool_get_risk":
            hours = int(args.get("hours", default_hours))
            tool_output = tool_get_risk(lat=lat, lng=lng, hours=hours)
            tool_outputs.append(tool_output)
            tool_results["risk"] = tool_output["result"]
            if not args.get("skip_upstream", False):
                upstream_output = tool_get_upstream_summary(lat=lat, lng=lng, hours=hours)
                tool_outputs.append(upstream_output)
                tool_results["upstream"] = upstream_output["result"]

        elif tool_name == "tool_get_upstream_summary":
            hours = int(args.get("hours", default_hours))
            tool_output = tool_get_upstream_summary(lat=lat, lng=lng, hours=hours)
            tool_outputs.append(tool_output)
            tool_results["upstream"] = tool_output["result"]

        elif tool_name == "tool_get_evac_centers":
            limit = int(args.get("limit", 3))
            tool_output = tool_get_evac_centers(lat=lat, lng=lng, limit=limit)
            evac_centers = tool_output["result"]
            tool_outputs.append(tool_output)
            tool_results["evac"] = tool_output["result"]

        elif tool_name == "tool_get_safe_route":
            if not evac_centers and tool_results.get("evac"):
                evac_centers = tool_results["evac"]

            if dest_lat is None and dest_lng is None:
                if evac_centers:
                    center = evac_centers[0]
                    dest_lat = center["latitude"]
                    dest_lng = center["longitude"]
                else:
                    return {
                        "reply": "No destination available for routing. Add destination coordinates or request an evacuation lookup first.",
                        "actions_taken": ["tool_get_safe_route"],
                        "tool_outputs": tool_outputs,
                    }

            mode = args.get("mode", "safest")
            route_payload = tool_get_safe_route(
                origin_lat=lat,
                origin_lng=lng,
                dest_lat=dest_lat,
                dest_lng=dest_lng,
                mode=mode,
            )
            tool_outputs.append(route_payload)
            tool_results["route"] = route_payload["result"]

        else:
            continue

    map_payload: dict[str, Any] | None = None
    if "route" in tool_results:
        route = tool_results["route"]
        map_payload = {
            "route": route.get("route", []),
            "origin_node": route.get("origin_node"),
            "destination_node": route.get("destination_node"),
            "mode": route.get("mode", "safest"),
            "type": "route",
        }
    elif "risk" in tool_results:
        risk_payload = tool_results["risk"]
        map_payload = {
            "lat": lat,
            "lng": lng,
            "risk_level": risk_payload["risk_level"],
            "risk_score": risk_payload["risk_score"],
            "type": "risk",
        }

    return {
        "reply": _build_conversational_reply(tool_results, language),
        "actions_taken": _plan_actions(tool_outputs),
        "tools_called": _plan_actions(tool_outputs),
        "tool_outputs": tool_outputs,
        "map_payload": map_payload,
    }
