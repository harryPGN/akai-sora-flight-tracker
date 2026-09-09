"""AKAI SORA — real-time flight tracker backend.

FastAPI app serving the static frontend plus JSON API endpoints:
  /api/flights         OpenSky state vectors in a bounding box
  /api/liveries        curated special-livery database
  /api/specs           aircraft engineering-spec database
  /api/weather         METAR for an airport (ICAO)
  /api/disruption      experimental airport disruption index
  /api/news            aviation news feed
  /api/predict         predicted future path for a flight
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import data as D
from . import opensky as OS
from . import weather as WX
from . import news as NEWS

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="AKAI SORA Flight Tracker", version="1.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "name": "AKAI SORA", "version": "1.0"}


@app.get("/api/flights")
def flights(
    lamin: float = Query(-90, ge=-90, le=90),
    lomin: float = Query(-180, ge=-180, le=180),
    lamax: float = Query(90, ge=-90, le=90),
    lomax: float = Query(180, ge=-180, le=180),
):
    if lamax < lamin or lomax < lomin:
        raise HTTPException(400, "Invalid bounding box")
    bbox = OS.BBox(lamin=lamin, lomin=lomin, lamax=lamax, lomax=lomax)
    return OS.fetch_flights(bbox)


@app.get("/api/liveries")
def liveries():
    return D.LIVERIES


@app.get("/api/specs")
def specs_list(q: str | None = None):
    items = list(D.SPECS.values())
    if q:
        ql = q.lower()
        items = [
            s for s in items
            if ql in s["model"].lower() or ql in s["typecode"].lower()
            or ql in s["manufacturer"].lower()
        ]
    return items


@app.get("/api/specs/{typecode}")
def spec_detail(typecode: str):
    s = D.spec_for(typecode)
    if not s:
        raise HTTPException(404, "Unknown type code")
    return s


@app.get("/api/weather")
def weather(airport: str):
    return WX.get_metar(airport)


@app.get("/api/disruption")
def disruption(airport: str):
    return WX.disruption_index(airport)


@app.get("/api/news")
def news():
    return NEWS.get_news()


@app.get("/api/predict")
def predict(icao24: str, minutes: float = 10.0):
    """Predicted path for the most recent known position of an aircraft.

    Tries the live OpenSky cache first, then demo data.
    """
    target = icao24.lower()
    flights = OS._last_good or []
    flight = next((f for f in flights if f["icao24"] == target), None)
    if flight is None:
        # search demo flights (already full flight dicts)
        for raw in D.DEMO_FLIGHTS.get("flights", []):
            if str(raw.get("icao24") or "").lower() == target:
                flight = OS.enrich(dict(raw))
                break
    if flight is None:
        raise HTTPException(404, "Aircraft not currently in view")
    path = OS.predict_path(flight, minutes=minutes)
    return {"icao24": target, "minutes": minutes, "path": path, "flight": flight}


# --- static frontend ---------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/{full_path:path}")
def spa(full_path: str):
    # serve other top-level static files if present, else index (SPA fallback)
    candidate = FRONTEND_DIR / full_path
    if candidate.is_file():
        return FileResponse(str(candidate))
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
