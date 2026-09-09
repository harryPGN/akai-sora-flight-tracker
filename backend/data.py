"""Data loading and livery / spec enrichment for AKAI SORA."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load(name: str) -> Any:
    with open(DATA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


SPECS_RAW: dict = _load("aircraftSpecs.json")
# normalise to a list of spec dicts (each carrying its typecode)
if isinstance(SPECS_RAW, dict):
    SPECS: dict[str, dict] = {k: v for k, v in SPECS_RAW.items()}
else:
    SPECS = {s["typecode"]: s for s in SPECS_RAW}
LIVERIES: list[dict] = _load("specialLiveries.json")
DEMO_FLIGHTS: list[dict] = _load("demoFlights.json")

# fast lookup maps
LIVERY_BY_ICAO: dict[str, dict] = {l["icao24"].lower(): l for l in LIVERIES}
LIVERY_BY_REG: dict[str, dict] = {l["registration"].lower(): l for l in LIVERIES}


def livery_for(icao24: str | None, registration: str | None) -> dict | None:
    if icao24 and icao24.lower() in LIVERY_BY_ICAO:
        return LIVERY_BY_ICAO[icao24.lower()]
    if registration and registration.lower() in LIVERY_BY_REG:
        return LIVERY_BY_REG[registration.lower()]
    return None


def spec_for(typecode: str | None) -> dict | None:
    if not typecode:
        return None
    return SPECS.get(typecode.upper())


# Map OpenSky aircraft "type" categories to a simple symbol family used by the
# frontend marker. OpenSky does not expose the ICAO type code, so we fall back
# to a category inferred from the OpenSky `category` field when present.
def symbol_family(category: int | None, typecode: str | None) -> str:
    if typecode:
        tc = typecode.upper()
        if tc.startswith(("EC", "AS", "H", "UH", "S", "B")):
            pass
    # OpenSky category codes (approximate): 1-3 light/medium, 4 large, 5-6 heavy,
    # 7 high perf, 8 rotorcraft, 9-10 glider/light, 11-19 ultralight.
    if category in (8,):
        return "rotorcraft"
    if category in (9, 10):
        return "light"
    if category in (1, 2, 3):
        return "medium"
    if category in (4,):
        return "large"
    if category in (5, 6, 7):
        return "heavy"
    return "medium"
