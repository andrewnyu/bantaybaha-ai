from dataclasses import dataclass

from .tool_router import run_tool_router

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


def run_chat_agent(message: str, context: ChatContext) -> dict:
    return run_tool_router(
        message=message,
        lat=context.lat,
        lng=context.lng,
        dest_lat=context.dest_lat,
        dest_lng=context.dest_lng,
        weather_mode="live",
        demo_rainfall=None,
    )
