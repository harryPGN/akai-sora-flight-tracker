# AKAI SORA · 紅空 — Real-Time Flight Tracker

A real-time flight tracker that goes beyond Flightradar24 / FlightAware — with deeper
engineering specs, special-livery alerts, and storm-aware features. Built as a student
portfolio project by an Aviation & Aeronautical Engineering student in Hong Kong.

## Features

- **Live Flight Tracking Map** — OpenSky Network state vectors with bounding-box
  filtering, 8 s polling, 4 s timeout and 30 s failure back-off. Aircraft markers
  rotate to true heading; on-ground aircraft are dimmed; markers match aircraft-type
  symbols. Click any aircraft for in-depth telemetry + a dead-reckoning predicted path.
- **Special Livery Tracker** — curated database of special-livery aircraft (Pokémon jets,
  batik & themed liveries). Gold-outlined markers when flying; "last known" status when
  ADS-B is off; photo of the livery on selection.
- **Aircraft Engineering Database** — engines, thrust, MTOW, range, ceiling, Mach, pax
  and more for 27 common types.
- **Home dashboard** — live aircraft-in-view count, curated livery & type counts,
  live METAR weather, an experimental airport disruption index, and aviation news.
- **Roadmap (future)** — weather-radar overlay + typhoon warning for flight paths
  intersecting a typhoon's forecast cone.

## Tech Stack

- **Backend:** Python · FastAPI · httpx
- **Frontend:** Vanilla HTML / CSS / JS · Leaflet · CARTO dark tiles
- **Data:** OpenSky Network (live states) · NOAA AviationWeather (METAR) ·
  Wikimedia Commons (livery imagery, license-safe)

## Run locally

```bash
cd akai-sora
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000

> OpenSky's anonymous endpoint is rate-limited and intermittently unavailable.
> The app falls back to a built-in demo dataset (clearly labelled) so the UI is
> never empty.

## Project structure

```
akai-sora/
├── backend/
│   ├── main.py          # FastAPI app + routes
│   ├── opensky.py       # OpenSky client: bbox, timeout, back-off, predicted path
│   ├── weather.py       # METAR + disruption index
│   ├── news.py          # aviation news (RSS + fallback)
│   ├── data.py          # data loading + livery/spec enrichment
│   └── data/            # JSON datasets
├── frontend/
│   ├── index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── requirements.txt
└── README.md
```

## Data sources & attribution

- Flight states: [OpenSky Network](https://opensky-network.org/) (CC BY 4.0)
- Weather: [NOAA AviationWeather](https://aviationweather.gov/)
- Livery photos: [Wikimedia Commons](https://commons.wikimedia.org/) (various free licenses)

For educational use.
