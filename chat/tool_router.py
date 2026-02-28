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


def _extract_number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None

    value = match.group(1)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _risk_context_from_payload(risk_payload: dict[str, Any]) -> dict[str, Any]:
    explanations = [str(item) for item in risk_payload.get("explanation", [])]
    window_hours = 3
    rain_mm = 0.0
    upstream_mm = 0.0
    has_upstream_signal = False
    for line in explanations:
        if window_match := re.search(r"Rainfall next (\d+)h", line):
            try:
                window_hours = int(window_match.group(1))
            except (TypeError, ValueError):
                window_hours = 3

        if "Rainfall next" in line:
            value = _extract_number(r"Rainfall next \d+h: ([0-9]+(?:\.[0-9]+)?)", line)
            if value is not None:
                rain_mm = value

        if "Upstream risk index" in line:
            value = _extract_number(
                r"Upstream risk index: ([0-9]+(?:\.[0-9]+)?)", line
            )
            if value is not None:
                upstream_mm = value

        if "Heavy rainfall detected upstream" in line:
            has_upstream_signal = True
            _ = _extract_number(r"downstream in ~([0-9]+(?:\.[0-9]+)?)", line)

    return {
        "window_hours": window_hours,
        "rain_mm": rain_mm,
        "upstream_mm": upstream_mm,
        "has_upstream_signal": has_upstream_signal,
        "explanations": explanations,
    }


def _build_conversational_reply(
    tool_results: dict[str, Any], language: str, forecast_hours: int = 3
) -> str:
    lang = _normalize_language(language)

    if lang == "tl":
        risk_high_label = "Panganib ng baha"
        low_risk_intro = (
            f"Walang natukoy na malaking rainfall o upstream impact para sa susunod na {forecast_hours} oras. "
            f"Sa ngayon, mukhang mababa ang panganib."
        )
        upstream_label = "Bagay sa itaas na bahagi"
        evac_label = "Pinakamalapit na evacuation center"
        route_label = "Ruta"
        no_data = "Wala pang sapat na data para bigyan ka ng malinaw na sagot."
        default_action = (
            "Maaari kong kunin ang risk, upstream rainfall signals, "
            "evacuation centers, at mga ruta. Subukan ang: "
            "\"check risk\", \"find nearest evacuation center\", o \"safe route to nearest evacuation center\"."
        )
        units_km = "km"
    elif lang == "ilo":
        risk_high_label = "Peligro"
        low_risk_intro = (
            f"Wala sang signal sang ulan ukon upstream impact para sa sunod nga {forecast_hours} oras. "
            f"Sa subong, nahanap naton nga hilum."
        )
        upstream_label = "Pagsulod sang ulan sa pinutikan"
        evac_label = "Pinakadaku nga evacuation center nga duul"
        route_label = "Ruta"
        no_data = "Wala pa gid sang igo nga data para magbalos sang sabat."
        default_action = (
            "Maka-check ako sang risk, upstream signals, evacuation centers, kag mga ruta. "
            "Pwede mo i-sabi: \"check risk\", \"find nearest evacuation center\", o \"safe route to nearest evacuation center\"."
        )
        units_km = "km"
    else:
        risk_high_label = "Flood risk is"
        low_risk_intro = (
            f"I don't see rainfall or upstream impact for the next {forecast_hours} hours. "
            "So there is currently no immediate flood risk signal."
        )
        upstream_label = "Upstream signal"
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

    parts = []
    if "risk" in tool_results:
        risk_payload = tool_results["risk"]
        risk_score = int(risk_payload.get("risk_score", 0))
        risk_level = risk_payload.get("risk_level", "UNKNOWN")
        risk_context = _risk_context_from_payload(risk_payload)
        window_hours = risk_context["window_hours"] or forecast_hours
        no_rainfall_impact = (
            risk_score <= 35
            and risk_context["rain_mm"] <= 0.0
            and risk_context["upstream_mm"] <= 0.0
            and not risk_context["has_upstream_signal"]
        )

        if no_rainfall_impact:
            parts.append(
                f"{low_risk_intro} "
                f"Score: {risk_score}/100 ({risk_level})."
            )
        else:
            if risk_score >= 65:
                parts.append(
                    f"{risk_high_label} HIGH ({risk_score}/100) for the next {window_hours} hours. "
                    "Please prepare and consider moving to safer ground."
                )
            elif risk_score >= 35:
                parts.append(
                    f"{risk_high_label} MEDIUM ({risk_score}/100) for the next {window_hours} hours. "
                    "Keep an eye on updates and avoid low-lying roads."
                )
            else:
                parts.append(
                    f"{risk_high_label} LOW ({risk_score}/100) for the next {window_hours} hours."
                )

        explanations = risk_payload.get("explanation")
        if explanations:
            summary = []
            for item in explanations:
                if "Rainfall next" in item or "Distance to nearest river" in item:
                    summary.append(item)
                elif "Upstream risk index" in item:
                    summary.append(item)
            if summary:
                parts.append("What I checked: " + "; ".join(summary))

    if "upstream" in tool_results:
        up = tool_results["upstream"]
        peak = up.get("expected_peak_in_hours")
        peak_text = f"~{peak}h" if peak is not None else "n/a"
        parts.append(
            f"{upstream_label}: {up['upstream_rain_index']} (normalized {up['upstream_rain_index_norm']}), "
            f"possible impact in {peak_text}."
        )

    if "evac" in tool_results:
        if tool_results["evac"]:
            first = tool_results["evac"][0]
            parts.append(
                f"{evac_label}: {first['name']} is {first['distance_km']} {units_km} away."
            )

    if "route" in tool_results:
        route = tool_results["route"]
        parts.append(
            f"{route_label} suggestion: about {route['total_distance']} {units_km}, "
            f"hazard exposure {route['hazard_exposure']} (mode: {route.get('mode', 'safest')})."
        )

    if not parts:
        return no_data

    return " ".join(parts)


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
        "reply": _build_conversational_reply(tool_results, language, requested_hours),
        "actions_taken": _plan_actions(tool_outputs),
        "tools_called": _plan_actions(tool_outputs),
        "tool_outputs": tool_outputs,
        "map_payload": map_payload,
    }
