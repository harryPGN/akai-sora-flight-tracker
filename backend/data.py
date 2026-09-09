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


# Map an aircraft type code to a marker symbol family used by the frontend.
# OpenSky's states/all endpoint does not expose the type code, so for arbitrary
# traffic we can only default to a generic jet; for liveries (where we know the
# type) and demo data we map the type code to the right silhouette.
_WIDEBODY = ("77", "78", "76", "74", "75", "33", "35", "34", "38", "31")  # 777/787/767/747/757/A330/A350/A340/A380/A310
_REGIONAL_TP = ("AT", "DH", "SF", "E", "Q", "DHC")  # turboprop / regional

def symbol_family(category: int | None, typecode: str | None) -> str:
    tc = (typecode or "").upper()
    if tc:
        # Airbus widebodies (A300/A310/A330/A340/A350/A380) vs narrow-body (A318-A321)
        if tc.startswith("A3"):
            if tc[2:3] in ("0", "1", "3", "4", "5", "8"):
                return "heavy"
            return "medium"
        # Boeing: ICAO designators like 77W, B789, B763, 738 — match first two digits
        is_boeing = (tc.startswith("7") and len(tc) >= 2 and tc[1].isdigit()) or \
                    (tc.startswith("B7") and len(tc) >= 3 and tc[2].isdigit())
        if is_boeing:
            fam = tc[1:3] if tc.startswith("B7") else tc[:2]  # 73,74,75,76,77,78
            if fam in ("74", "76", "77", "78"):
                return "heavy"
            return "medium"
        # turboprop / regional
        if tc.startswith(("AT", "DH", "SF", "DHC")) or tc in ("AT7", "AT72", "DH8", "DHC8", "SF34"):
            return "turboprop"
        # rotorcraft
        if tc.startswith(("EC", "AS", "UH", "B06", "S76", "AW")) or tc.startswith("H"):
            return "rotorcraft"
        # light / general
        if tc.startswith(("BE", "C5", "C7", "PC", "M2", "LJ", "F9", "GL")):
            return "light"
        return "medium"            # narrow-body jet fallback
    # fall back to OpenSky category codes if a caller has them
    if category == 8:
        return "rotorcraft"
    if category in (9, 10):
        return "light"
    if category in (5, 6, 7):
        return "heavy"
    if category == 4:
        return "large"
    return "medium"
