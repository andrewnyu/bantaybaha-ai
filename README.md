# Bantay Baha AI MVP (Django)

Minimal hackathon MVP for:
- 1-6 hour flood risk estimation
- nearest evacuation center lookup
- safer routing around flood-prone zones
- rule-based chat endpoint that orchestrates these tools

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Generate Negros Data (required for accurate area/risk maps)

The following files are stored locally and excluded from git by `.gitignore`:

- `data/negros_graph.graphml`
- `data/negros_rivers.geojson`
- `data/river_sample_points.json`
- `data/negros_river_graph.gpickle`

Run once (or whenever files are deleted):

```bash
source .venv/bin/activate
python scripts/load_negros_roads.py
python scripts/build_river_graph.py
```

Open `http://127.0.0.1:8000/`.

## API Endpoints

- `GET /api/risk/?lat=14.60&lng=121.00&hours=3`
- `GET /api/evac-centers/?lat=14.60&lng=121.00`
- `GET /api/safe-route/?origin_lat=14.60&origin_lng=121.00&dest_lat=14.64&dest_lng=121.09&mode=safe`
- `POST /api/chat/` with JSON body `{ "message": "risk and evac" }`
