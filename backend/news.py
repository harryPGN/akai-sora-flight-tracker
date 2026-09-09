"""Aviation news fetcher with curated fallback.

Tries public RSS feeds; falls back to a curated list if all fail.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import httpx

UA = "AkaiSora-FlightTracker/1.0 (student project)"

FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/SB10001424053111904308204583470903544709282",
    "https://www.aviationnow.com/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
]

FALLBACK = [
    {
        "title": "China Airlines debuts Pikachu Jet CI2 on A350",
        "summary": "Taiwan's flag carrier launched a second Pokémon-themed livery on an Airbus A350.",
        "link": "https://www.china-airlines.com/",
        "source": "Curated",
    },
    {
        "title": "ANA reveals 'Green Pokémon Jet' for 30-year Pokémon partnership",
        "summary": "A Boeing 787-9 joins ANA's fleet of special Pokémon liveries.",
        "link": "https://www.anahd.co.jp/group/en/pr/202608/20260824.html",
        "source": "Curated",
    },
    {
        "title": "OpenSky Network expands real-time ADS-B coverage",
        "summary": "The open OpenSky Network provides live aircraft state vectors used by AKAI SORA.",
        "link": "https://opensky-network.org/",
        "source": "Curated",
    },
    {
        "title": "Sustainable aviation fuel milestones continue in Asia",
        "summary": "Carriers across the region advance SAF adoption on select routes.",
        "link": "https://www.iata.org/",
        "source": "Curated",
    },
]

_cache: tuple[float, list[dict]] | None = None


def _parse_rss(xml: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title and link:
            # strip simple HTML tags from description
            import re
            desc = re.sub("<[^>]+>", "", desc)[:200]
            items.append({
                "title": title,
                "summary": desc or title,
                "link": link,
                "source": "RSS",
                "date": pub,
            })
    return items


def get_news() -> list[dict]:
    global _cache
    now = time.time()
    if _cache and now - _cache[0] < 600:
        return _cache[1]
    items: list[dict] = []
    for url in FEEDS:
        try:
            with httpx.Client(timeout=5.0, headers={"User-Agent": UA}) as client:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()
                items = _parse_rss(resp.text)
            if items:
                break
        except Exception:
            continue
    if not items:
        items = FALLBACK
    else:
        items = items[:12]
    _cache = (now, items)
    return items
