"""OpenSky Network client with bbox filtering, timeout, back-off and demo fallback.

Reference: https://opensky-network.org/apidoc/rest
States are returned as arrays in a fixed column order (see IDX below).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict
from typing import Any

import httpx

from . import data as D
from . import airports as AP

OPENSKY_URL = "https://opensky-network.org/api/states/all"
TIMEOUT = 4.0          # 4s timeout per the spec
BACKOFF = 30.0         # 30s failure back-off
UA = "AkaiSora-FlightTracker/1.0 (student project)"

# OpenSky state-vector column indices
IDX = {
    "icao24": 0,
    "callsign": 1,
    "origin_country": 2,
    "time_position": 3,
    "last_contact": 4,
    "longitude": 5,
    "latitude": 6,
    "baro_altitude": 7,
    "on_ground": 8,
    "velocity": 9,
    "true_track": 10,
    "vertical_rate": 11,
    "geo_altitude": 13,
    "squawk": 14,
    "spi": 15,
    "position_source": 16,
}

_last_failure = 0.0
_last_good: list[dict] | None = None

# rolling per-aircraft position history (for 'landed / ADS-B off' last pathway).
# only tracked for known special liveries to bound memory.
_history: dict[str, list[dict]] = {}
HISTORY_MAX = 120  # ~16 minutes at 8s polling


def _record_history(flights: list[dict]):
    now = int(time.time())
    for f in flights:
        icao = f.get("icao24")
        lat, lon = f.get("latitude"), f.get("longitude")
        if not icao or lat is None or lon is None:
            continue
        if icao not in D.LIVERY_BY_ICAO:
            continue
        path = _history.setdefault(icao, [])
        path.append({"lat": lat, "lon": lon, "ts": now, "alt": f.get("baroAltitude"), "gs": f.get("velocity"), "trk": f.get("trueTrack")})
        if len(path) > HISTORY_MAX:
            path.pop(0)


def livery_status(icao24: str) -> dict:
    """Status of a special-livery aircraft: flying now, or last known path + nearest airport."""
    icao = icao24.lower()
    pool = _last_good or _demo_flights()
    current = next((f for f in pool if f["icao24"] == icao), None)
    has_pos = bool(current and current.get("latitude") is not None)
    if has_pos:
        ap = AP.nearest(current["latitude"], current["longitude"])
        if current.get("onGround"):
            return {"icao24": icao, "status": "on_ground", "flight": current, "nearestAirport": ap}
        return {"icao24": icao, "status": "flying", "flight": current, "nearestAirport": ap}
    path = _history.get(icao, [])
    if path:
        last = path[-1]
        ap = AP.nearest(last["lat"], last["lon"])
        return {"icao24": icao, "status": "landed_or_off",
                "lastPath": path, "lastSeen": last["ts"], "nearestAirport": ap}
    return {"icao24": icao, "status": "unknown",
            "note": "Not yet observed transmitting on OpenSky in this session."}


@dataclass
class BBox:
    lamin: float
    lomin: float
    lamax: float
    lomax: float


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def enrich(f: dict) -> dict:
    """Attach livery + spec + symbol info to a parsed flight dict."""
    icao24 = str(f.get("icao24") or "").lower()
    livery = D.livery_for(icao24, f.get("registration"))
    typecode = (livery or {}).get("typecode") or f.get("typecode")
    f["typecode"] = typecode
    if livery:
        f["livery"] = livery["liveryName"]
        f["registration"] = livery["registration"]
    elif "livery" not in f:
        f["livery"] = None
    f["symbol"] = D.symbol_family(None, typecode)
    return f


def parse_state(s: list) -> dict:
    icao24 = str(s[IDX["icao24"]] or "").lower()
    callsign = str(s[IDX["callsign"]] or "").strip() or None
    return enrich({
        "icao24": icao24,
        "callsign": callsign,
        "originCountry": str(s[IDX["origin_country"]] or "Unknown"),
        "longitude": _num(s[IDX["longitude"]]),
        "latitude": _num(s[IDX["latitude"]]),
        "baroAltitude": _num(s[IDX["baro_altitude"]]),
        "geoAltitude": _num(s[IDX["geo_altitude"]]),
        "onGround": bool(s[IDX["on_ground"]]),
        "velocity": _num(s[IDX["velocity"]]),          # m/s
        "trueTrack": _num(s[IDX["true_track"]]),       # deg
        "verticalRate": _num(s[IDX["vertical_rate"]]),  # m/s
        "squawk": str(s[IDX["squawk"]] or "") if s[IDX["squawk"]] else None,
        "spi": bool(s[IDX["spi"]]),
        "positionSource": int(s[IDX["position_source"]] or 0),
        "lastContact": int(s[IDX["last_contact"]] or time.time()),
        "typecode": None,
        "livery": None,
        "registration": None,
        "symbol": "medium",
    })


def in_bbox(f: dict, b: BBox) -> bool:
    if f["latitude"] is None or f["longitude"] is None:
        return False
    return (
        b.lamin <= f["latitude"] <= b.lamax
        and b.lomin <= f["longitude"] <= b.lomax
    )


def _apply_drift(f: dict, elapsed: float) -> dict:
    """Gentle time-based drift so demo flights feel live."""
    if f["onGround"] or f["velocity"] is None or f["trueTrack"] is None:
        return f
    if f["latitude"] is None or f["longitude"] is None:
        return f
    speed = min(f["velocity"], 320) * 0.15
    dist = speed * elapsed  # metres
    m_per_deg = 111320.0
    tr = math.radians(f["trueTrack"])
    dlat = dist * math.cos(tr) / m_per_deg
    denom = m_per_deg * (math.cos(math.radians(f["latitude"])) or 1.0)
    dlon = dist * math.sin(tr) / denom
    dlat = max(-3.0, min(3.0, dlat))
    dlon = max(-3.0, min(3.0, dlon))
    out = dict(f)
    out["latitude"] = f["latitude"] + dlat
    out["longitude"] = f["longitude"] + dlon
    out["lastContact"] = int(time.time())
    return out


def _demo_flights() -> list[dict]:
    now = time.time()
    demo = D.DEMO_FLIGHTS
    base_epoch = demo.get("generatedAt") or demo.get("baseEpoch") or (now - 60)
    out: list[dict] = []
    for raw in demo.get("flights", []):
        f = enrich(dict(raw))
        out.append(_apply_drift(f, now - float(base_epoch)))
    return out


def fetch_flights(bbox: BBox | None) -> dict:
    """Return flights in bbox. Falls back to demo data on failure/back-off."""
    global _last_failure, _last_good
    now = time.time()
    in_backoff = now - _last_failure < BACKOFF

    flights: list[dict] = []
    source = "opensky"
    cached_at = int(now)

    if not in_backoff:
        params = {}
        if bbox:
            params = {
                "lamin": bbox.lamin, "lomin": bbox.lomin,
                "lamax": bbox.lamax, "lomax": bbox.lomax,
            }
        try:
            with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}) as client:
                resp = client.get(OPENSKY_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
            states = payload.get("states") or []
            for s in states:
                try:
                    f = parse_state(s)
                except Exception:
                    continue
                if bbox and not in_bbox(f, bbox):
                    continue
                flights.append(f)
            _last_good = flights
            cached_at = int(payload.get("time") or now)
            _record_history(flights)
        except Exception:
            _last_failure = now
            flights = _last_good or _demo_flights()
            source = "demo" if not _last_good else "cached"
            cached_at = int(now)
    else:
        flights = _last_good or _demo_flights()
        source = "demo" if not _last_good else "cached"

    livery_matches = sorted({f["icao24"] for f in flights if f.get("livery")})
    return {
        "source": source,
        "time": cached_at,
        "count": len(flights),
        "cachedAt": cached_at,
        "flights": flights,
        "liveryMatches": livery_matches,
    }


def predict_path(flight: dict, minutes: float = 10.0, step_km: float = 50.0) -> list[list[float]]:
    """Simple dead-reckoning estimate of the future ground track.

    Not ATC-grade. Uses ground speed + true heading over `minutes`.
    Returns a list of [lat, lon] points including the current position.
    """
    lat = flight.get("latitude")
    lon = flight.get("longitude")
    vel = flight.get("velocity")  # m/s
    track = flight.get("trueTrack")
    on_ground = flight.get("onGround")
    if lat is None or lon is None or on_ground or vel is None or track is None:
        return [[lat, lon]] if lat is not None and lon is not None else []

    seconds = minutes * 60.0
    total_dist = vel * seconds  # metres
    # generate points every step_km along the path
    n = max(2, int(total_dist / (step_km * 1000)) + 1)
    pts: list[list[float]] = [[lat, lon]]
    tr = math.radians(track)
    m_per_deg = 111320.0
    cos_lat = math.cos(math.radians(lat)) or 1.0
    for i in range(1, n + 1):
        frac = i / n
        d = total_dist * frac
        dlat = d * math.cos(tr) / m_per_deg
        dlon = d * math.sin(tr) / (m_per_deg * cos_lat)
        pts.append([lat + dlat, lon + dlon])
    return pts
