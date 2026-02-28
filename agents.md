# BahaWatch PH – Agent Guidelines

## Context

This project is built for a **7-hour hackathon**.

The goal is to deliver a working MVP demonstrating:

1. Flood risk estimation (next 1–6 hours)
2. Nearest evacuation center lookup
3. Safe route computation avoiding flood-prone areas
4. A simple agentic chat interface that orchestrates the above

This is NOT a production system.
This is NOT a research-grade flood simulator.
This is NOT a scalable disaster management platform.

It is a fast, working demo.

---

# 🚨 CRITICAL PRINCIPLES

## 1️⃣ Avoid Over-Engineering

DO NOT:

- Add microservices
- Add Celery or background workers
- Add Redis
- Add Kubernetes
- Add Docker orchestration unless trivial
- Add authentication or user accounts
- Add complex ML training pipelines
- Add heavy raster processing pipelines
- Add streaming systems
- Add event-driven architectures

Everything runs inside ONE Django project.

---

## 2️⃣ Prefer Simple Heuristics Over Complex Models

Flood risk is calculated using:

- Simple weighted scoring
- Simulated or lightweight data
- Basic GeoPandas / Shapely logic
- Mock rainfall data if needed

DO NOT:
- Implement deep learning
- Build training pipelines
- Overcomplicate feature engineering
- Fetch large external datasets dynamically

This is a demo.

---

## 3️⃣ Keep Dependencies Minimal

Allowed:
- Django
- GeoPandas
- Shapely
- NetworkX
- Requests
- Leaflet (frontend only)

Avoid adding anything else unless absolutely necessary.

---

## 4️⃣ Single Responsibility Modules

Keep logic organized but simple:

- risk/risk_engine.py
- routing/routing_engine.py
- chat/chat_agent.py

No abstraction layers beyond that.

No service containers.
No dependency injection frameworks.

---

## 5️⃣ Data Should Be Lightweight

Use:

- Small mock GeoJSON files
- Small sample road graph JSON
- Simple evacuation center fixtures

Do NOT download full national datasets.
Do NOT load massive OSM extracts.
Do NOT require PostGIS.

SQLite is enough.

---

## 6️⃣ Agentic Chat is Rule-Based

The “agent” is:

- Simple intent detection via keyword matching
- Calls internal functions directly
- Returns structured response

Do NOT:
- Integrate external LLM APIs
- Add complex prompt orchestration
- Build memory systems
- Implement tool registries

Keep it deterministic and demo-safe.

---

# 🎯 Definition of Done

The project is complete when:

- `/api/risk/` returns a reasonable risk score
- `/api/evac-centers/` returns nearest centers
- `/api/safe-route/` returns a path avoiding high hazard edges
- `/api/chat/` can trigger those tools
- A simple Leaflet map shows interaction

That’s it.

---

# ⏳ Time Discipline

Remember:

We have 7 hours.

Time priority:

1. Risk endpoint works
2. Evac center lookup works
3. Safe route works
4. Chat wrapper works
5. UI polish (if time remains)

If something becomes complex:
→ simplify
→ mock
→ simulate
→ hardcode

Shipping > perfection.

---

# 🧠 Philosophy

This is about:

Actionable flood intelligence.
Clear demo.
Strong pitch.

Not technical perfection.

If unsure between:
- Complex + “cool”
- Simple + working

Choose simple + working.

Always.