"""Nearest-airport lookup for the 'landed / ADS-B off' livery status.

A compact set of major world airports (ICAO, IATA, name, lat, lon).
nearest(lat, lon) returns the closest airport by great-circle distance.
"""
from __future__ import annotations

import math

AIRPORTS = [
    ("VHHH", "HKG", "Hong Kong Intl", 22.3089, 113.9145),
    ("VMMC", "MFM", "Macau Intl", 22.1496, 113.5916),
    ("ZGGG", "CAN", "Guangzhou Baiyun", 23.3924, 113.2988),
    ("ZGSZ", "SZX", "Shenzhen Bao'an", 22.6393, 113.8108),
    ("ZBAA", "PEK", "Beijing Capital", 40.0801, 116.5846),
    ("ZSPD", "PVG", "Shanghai Pudong", 31.1443, 121.8083),
    ("ZSSS", "SHA", "Shanghai Hongqiao", 31.1979, 121.3364),
    ("RCTP", "TPE", "Taipei Taoyuan", 25.0777, 121.2328),
    ("RCSS", "TSA", "Taipei Songshan", 25.0697, 121.5519),
    ("RJTT", "HND", "Tokyo Haneda", 35.5494, 139.7798),
    ("RJAA", "NRT", "Tokyo Narita", 35.7720, 140.3929),
    ("RJBB", "KIX", "Osaka Kansai", 34.4347, 135.2440),
    ("RJOO", "ITM", "Osaka Itami", 34.7855, 135.4382),
    ("RKSI", "ICN", "Seoul Incheon", 37.4602, 126.4407),
    ("RKSS", "GMP", "Seoul Gimpo", 37.5583, 126.7906),
    ("WSSS", "SIN", "Singapore Changi", 1.3644, 103.9915),
    ("WMKK", "KUL", "Kuala Lumpur Intl", 2.7456, 101.7099),
    ("VTBS", "BKK", "Bangkok Suvarnabhumi", 13.6900, 100.7501),
    ("VTBD", "DMK", "Bangkok Don Mueang", 13.9126, 100.6068),
    ("VIDP", "DEL", "Delhi Indira Gandhi", 28.5562, 77.1000),
    ("VABB", "BOM", "Mumbai Chhatrapati Shivaji", 19.0896, 72.8656),
    ("OMDB", "DXB", "Dubai Intl", 25.2532, 55.3657),
    ("OTHH", "DOH", "Doha Hamad", 25.2731, 51.6080),
    ("EGKK", "LGW", "London Gatwick", 51.1481, -0.1903),
    ("EGLL", "LHR", "London Heathrow", 51.4700, -0.4543),
    ("LFPG", "CDG", "Paris Charles de Gaulle", 49.0040, 2.5533),
    ("EDDF", "FRA", "Frankfurt am Main", 50.0379, 8.5622),
    ("EHAM", "AMS", "Amsterdam Schiphol", 52.3105, 4.7683),
    ("LEMD", "MAD", "Madrid Barajas", 40.4983, -3.5676),
    ("LIRF", "FCO", "Rome Fiumicino", 41.8003, 12.2389),
    ("UUEE", "SVO", "Moscow Sheremetyevo", 55.9728, 37.4147),
    ("KLAX", "LAX", "Los Angeles Intl", 33.9416, -118.4085),
    ("KJFK", "JFK", "New York John F Kennedy", 40.6413, -73.7781),
    ("KEWR", "EWR", "Newark Liberty", 40.6895, -74.1745),
    ("KORD", "ORD", "Chicago O'Hare", 41.9742, -87.9073),
    ("CYYZ", "YYZ", "Toronto Pearson", 43.6777, -79.6248),
    ("SBGR", "GRU", "São Paulo Guarulhos", -23.4356, -46.4731),
    ("YSSY", "SYD", "Sydney Kingsford Smith", -33.9399, 151.1753),
    ("NZAA", "AKL", "Auckland Intl", -37.0082, 174.7850),
    ("ZGSZ", "SZX", "Shenzhen Bao'an", 22.6393, 113.8108),
]


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p = math.radians(lat1)
    q = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p) * math.cos(q) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float):
    best = None
    best_d = float("inf")
    for icao, iata, name, la, lo in AIRPORTS:
        d = _haversine_km(lat, lon, la, lo)
        if d < best_d:
            best_d = d
            best = (icao, iata, name, la, lo)
    if best is None:
        return None
    return {
        "icao": best[0], "iata": best[1], "name": best[2],
        "lat": best[3], "lon": best[4], "distanceKm": round(best_d, 1),
    }
