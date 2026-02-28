# Bantay Baha AI

An emergency-response MVP for Negros hazard forecasting and evacuation assistance, built in Django.

## Project goal

- 1-6 hour flood risk estimation for a selected coordinate
- nearest evacuation center lookup
- safe route planning that avoids flood-prone edges
- single chat endpoint that orchestrates all three tools
- local-language outputs (English, Tagalog, and Hiligaynon/Cebuano intent handling)

## Read this README like judges will

### 1) Clarity of code

All logic is kept to three focused engines.

- `risk/risk_engine.py` handles risk input fusion, scoring, and projection outputs.
- `routing/routing_engine.py` handles road graph loading and risk-aware route search.
- `chat/chat_agent.py` handles intent matching and deterministic tool orchestration.
- API views stay thin and call only one engine per use case.

### 2) Technical execution

The system is intentionally lightweight but production-directional.

- Risk is estimated from multiple practical signals: elevation, river proximity, current rainfall, and forecast rainfall.
- Route planning is constrained by flood hazard weight instead of just shortest distance.
- Every endpoint returns structured JSON for predictable front-end rendering.
- Chat orchestration is deterministic and safe for demo reliability.

### 3) Completeness

This MVP includes the required endpoints and demos for the hackathon scope.

- `GET /api/risk/`
- `GET /api/evac-centers/`
- `GET /api/safe-route/`
- `POST /api/chat/`
- local demo mode for repeatable typhoon scenario testing

### 4) Impact and insight

Designed for the real response loop:  
risk signal → evacuation search → route selection → plain-language guidance.

The chat response includes context metadata (hazard level, nearest center, route status, and confidence notes), which helps a person make a fast decision instead of reading raw sensor values.

### 5) Use of Codex

This project was iterated and refined with Codex as a coding assistant for rapid planning, architecture shaping, endpoint wiring, and documentation updates under hackathon time constraints.

## What the system estimates

Risk scoring is heuristic and explicit.

- Elevation: lower elevations increase flood vulnerability.
- River network: proximity to modeled river geometry increases baseline risk.
- Weather: current rainfall and requested hourly forecast shape short-term severity.
- Spatial influence: nearby high-risk nodes can propagate urgency to adjacent area.
- Final score: normalized blend of those factors, bounded for stable UI labels and route weighting.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Data prerequisites

Area-specific files are local and ignored from git:

- `data/negros_graph.graphml`
- `data/negros_rivers.geojson`
- `data/river_sample_points.json`
- `data/negros_river_graph.gpickle`

Generate once per fresh clone:

```bash
source .venv/bin/activate
python scripts/load_negros_roads.py
python scripts/build_river_graph.py
```

## API reference

### Flood risk

`GET /api/risk/?lat=14.60&lng=121.00&hours=3`

Expected response shape:

```json
{
  "risk_level": "moderate|high|low",
  "score": 0.68,
  "hours": [
    {"hour": 1, "score": 0.72}
  ],
  "insight": "Flood risk rising due to heavy upstream input and low-elevation area."
}
```

### Evacuation centers

`GET /api/evac-centers/?lat=14.60&lng=121.00`

### Safe route

`GET /api/safe-route/?origin_lat=14.60&origin_lng=121.00&dest_lat=14.64&dest_lng=121.09&mode=safe`

Route modes include:
- safe
- fast
- safest

### Chat orchestration

`POST /api/chat/`

```json
{
  "message": "risk and evac",
  "lat": 14.60,
  "lng": 121.00
}
```

Example intents:
- `{"message": "check flood risk near me", "lat": 14.6, "lng": 121.0}`
- `{"message": "find nearest evacuation center", "lat": 14.6, "lng": 121.0}`
- `{"message": "find safe route to nearest evac", "lat": 14.6, "lng": 121.0, "dest_lat": 14.64, "dest_lng": 121.09}`

## Demo mode (Typhoon scenarios)

Use these optional query/body parameters to run predictable test cases:

- `weather_mode=demo`
- `demo_rainfall=80,90,75,40,10,0`
- `demo_upstream_rainfall=[{"lat":14.6001,"lng":121.0002,"demo_rainfall":[50,40,30]}]`

Risk demo:

```bash
curl "http://127.0.0.1:8000/api/risk/?lat=14.60&lng=121.00&hours=3&weather_mode=demo&demo_rainfall=80,90,75,40,10,0"
```

Route demo:

```bash
curl "http://127.0.0.1:8000/api/safe-route/?origin_lat=14.60&origin_lng=121.00&dest_lat=14.64&dest_lng=121.09&hours=4&mode=safest&weather_mode=demo&demo_rainfall=80,90,75,40,10,0"
```

Chat demo payload:

```json
{
  "message": "check risk",
  "lat": 14.60,
  "lng": 121.00,
  "weather_mode": "demo",
  "demo_rainfall": [10, 22, 45, 30, 12, 5]
}
```

## Live mode

Default behavior uses configured weather API data for current and forecast rainfall.

```bash
curl "http://127.0.0.1:8000/api/risk/?lat=14.60&lng=121.00&hours=3"
```

<p align="center">
  <img src="./bantay-baha-ai-logo.png" alt="Bantay Baha AI Logo" style="max-width: 35%; width: auto; height: auto;" />
</p>
