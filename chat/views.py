import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .chat_agent import ChatContext, run_chat_agent


@csrf_exempt
@require_POST
def chat_api(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    message = payload.get("message", "").strip()
    if not message:
        return JsonResponse({"error": "message is required"}, status=400)

    try:
        context = ChatContext(
            lat=float(payload.get("lat", ChatContext.lat)),
            lng=float(payload.get("lng", ChatContext.lng)),
            dest_lat=float(payload.get("dest_lat", ChatContext.dest_lat)),
            dest_lng=float(payload.get("dest_lng", ChatContext.dest_lng)),
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "lat/lng/dest_lat/dest_lng must be numeric when provided"},
            status=400,
        )

    result = run_chat_agent(message, context)
    return JsonResponse(result)
