"""Airport weather (METAR) and disruption-index services.

Data: U.S. NOAA AviationWeather.gov JSON API (no key required).
Docs: https://aviationweather.gov/data/api/
"""
from __future__ import annotations

import time

import httpx

UA = "AkaiSora-FlightTracker/1.0 (student project)"
API = "https://aviationweather.gov/api/data/metar"

_cache: dict[str, tuple[float, dict]] = {}
TTL = 300.0


def _ft_to_m(ft: float | None) -> float | None:
    return None if ft is None else ft * 0.3048


def _visib_to_m(vis: str | None) -> float | None:
    """Convert visib like '6+' (miles) to metres. '6+' means >=6 miles."""
    if not vis:
        return None
    v = vis.replace("+", "").replace(" ", "")
    try:
        miles = float(v)
    except ValueError:
        return None
    return miles * 1609.344


def get_metar(icao: str) -> dict:
    icao = icao.upper().strip()
    now = time.time()
    if icao in _cache and now - _cache[icao][0] < TTL:
        return _cache[icao][1]

    result: dict = {"station": icao, "available": False, "fetchedAt": int(now)}
    try:
        with httpx.Client(timeout=6.0, headers={"User-Agent": UA}) as client:
            resp = client.get(API, params={"ids": icao, "format": "json"})
            resp.raise_for_status()
            data = resp.json()
        arr = data if isinstance(data, list) else data.get("data", [])
        if arr:
            m = arr[0]
            clouds = m.get("clouds") or []
            ceiling_ft = None
            for c in clouds:
                if c.get("cover") in ("BKN", "OVC") and c.get("base") is not None:
                    base = float(c["base"])
                    if ceiling_ft is None or base < ceiling_ft:
                        ceiling_ft = base
            result = {
                "station": m.get("icaoId", icao),
                "name": m.get("name"),
                "raw": m.get("rawOb"),
                "available": True,
                "fetchedAt": int(now),
                "obsTime": m.get("obsTime"),
                "temperatureC": m.get("temp"),
                "dewpointC": m.get("dewp"),
                "windDir": m.get("wdir"),
                "windSpeedKt": m.get("wspd"),
                "windGustKt": m.get("gust"),
                "visibilityM": _visib_to_m(m.get("visib")),
                "ceilingM": _ft_to_m(ceiling_ft),
                "altimHpa": m.get("altim"),
                "cover": m.get("cover"),
                "clouds": clouds,
                "fltCat": m.get("fltCat"),
                "lat": m.get("lat"),
                "lon": m.get("lon"),
                "elevM": m.get("elev"),
            }
        else:
            result["error"] = "No METAR available for station"
    except Exception as e:
        result["error"] = str(e)
    _cache[icao] = (now, result)
    return result


def disruption_index(icao: str) -> dict:
    """Experimental 0-100 disruption index derived from the latest METAR."""
    metar = get_metar(icao)
    if not metar.get("available"):
        return {"station": icao.upper(), "index": None, "label": "No data",
                "factors": {}, "metar": metar}
    score = 0.0
    factors: dict[str, float] = {}
    wind = metar.get("windSpeedKt")
    if wind is not None:
        w = min(40.0, float(wind)) / 40.0 * 35.0
        score += w
        factors["wind"] = round(w, 1)
    vis = metar.get("visibilityM")
    if vis is not None:
        v = max(0.0, 1.0 - min(vis, 10000.0) / 10000.0) * 30.0
        score += v
        factors["lowVisibility"] = round(v, 1)
    ceil = metar.get("ceilingM")
    if ceil is not None:
        c = max(0.0, 1.0 - min(ceil, 3000.0) / 3000.0) * 20.0
        score += c
        factors["lowCeiling"] = round(c, 1)
    cat = (metar.get("fltCat") or "").upper()
    cat_pen = {"LIFR": 15.0, "IFR": 10.0, "MVFR": 5.0}.get(cat, 0.0)
    if cat_pen:
        score += cat_pen
        factors["flightCategory"] = round(cat_pen, 1)
    idx = int(max(0.0, min(100.0, score)))
    label = ("Minimal" if idx < 20 else "Low" if idx < 40
             else "Moderate" if idx < 60 else "High" if idx < 80 else "Severe")
    return {
        "station": icao.upper(),
        "index": idx,
        "label": label,
        "factors": factors,
        "metar": metar,
        "experimental": True,
    }
