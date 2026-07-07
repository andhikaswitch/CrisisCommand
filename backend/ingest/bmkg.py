"""BMKG earthquake ingestor — Indonesia's official geophysics agency feed.

Public open-data endpoint (no key): recent M5+ earthquakes with tsunami
potential flags. Regional-official coverage for the demo's home region and a
nice dedup showcase: a big Indonesian quake arrives from BOTH USGS and BMKG,
and the GPU cosine+distance dedup merges them into one marker.

Feed shape (data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json):
  {"Infogempa": {"gempa": [{"DateTime": "...+00:00", "Coordinates": "lat,lon",
    "Magnitude": "5.6", "Wilayah": "...", "Potensi": "..."}]}}

Failure handling identical to the other ingestors: any error logs and
returns [] — a dead feed never crashes the app (ARCHITECTURE.md §8).
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.ingest import normalizer
from backend.models import CrisisEvent

logger = logging.getLogger(__name__)

SOURCE = "BMKG"
# Two open-data feeds, merged: M5+ recent quakes and "felt" quakes (includes
# M3-4 that people reported feeling). Overlapping entries share the same
# timestamp-derived id and collapse naturally. BMKG's Twitter firehose also
# posts micro-quakes (M<3) that never reach these JSON feeds — those are
# below crisis-tool relevance anyway.
DEFAULT_FEED = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"
FELT_FEED = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


def parse_feed(payload: dict) -> list[CrisisEvent]:
    """Map a BMKG gempaterkini payload to CrisisEvents (pure, unit-testable)."""
    events: list[CrisisEvent] = []
    for item in (payload.get("Infogempa", {}) or {}).get("gempa", []) or []:
        try:
            lat_s, lon_s = (item.get("Coordinates") or "").split(",")
            lat, lon = float(lat_s), float(lon_s)
            mag = float(item.get("Magnitude"))
            when = normalizer.parse_iso_utc(item["DateTime"])
            region = (item.get("Wilayah") or "Indonesia").strip()
            tsunami_potential = "berpotensi" in (item.get("Potensi") or "").lower() \
                and "tidak" not in (item.get("Potensi") or "").lower()
            severity = normalizer.normalize_severity_usgs(mag)
            if tsunami_potential:
                # An official tsunami-potential flag is a severity signal in
                # itself; floor it at the red band.
                severity = max(severity, 0.75)
            events.append(
                normalizer.make_event(
                    id=f"bmkg-{when.strftime('%Y%m%d%H%M%S')}",
                    kind="earthquake",
                    title=f"M{mag} earthquake, {region}",
                    lat=lat,
                    lon=lon,
                    country="Indonesia",
                    severity=severity,
                    started_at=when,
                    source=SOURCE,
                    source_url="https://www.bmkg.go.id/gempabumi/gempabumi-terkini.bmkg",
                    raw={"magnitude": mag, "potensi": item.get("Potensi"),
                         "kedalaman": item.get("Kedalaman")},
                )
            )
        except (KeyError, ValueError, TypeError, AttributeError, IndexError) as exc:
            logger.warning("BMKG: skipping malformed item: %s", exc)
    return events


async def fetch(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    urls = [
        os.getenv("BMKG_FEED_URL", DEFAULT_FEED),
        os.getenv("BMKG_FELT_FEED_URL", FELT_FEED),
    ]
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    events: dict[str, CrisisEvent] = {}
    try:
        for url in urls:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                for e in parse_feed(resp.json()):
                    events[e.id] = e  # same quake in both feeds -> one entry
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("BMKG feed %s unavailable, skipping: %s", url, exc)
        logger.info("BMKG: ingested %d earthquake events", len(events))
        return list(events.values())
    finally:
        if own:
            await client.aclose()
