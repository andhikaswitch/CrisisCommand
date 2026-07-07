"""USGS earthquake ingestor — public GeoJSON feed (ARCHITECTURE.md §3).

Fetch → map each feature to a CrisisEvent → return. All USGS-specific quirks
live here; shared severity/timestamp logic is in normalizer.py. Any fetch or
parse failure logs and yields an empty list — a dead feed never crashes the
app, it just leaves the existing events untouched (failure mode §8).
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.ingest import normalizer
from backend.models import CrisisEvent

logger = logging.getLogger(__name__)

SOURCE = "USGS"
# M4.5+ past day: enough real events to populate the globe without flooding it.
DEFAULT_FEED = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
)
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


def _country_from_place(place: str) -> str:
    if not place:
        return "Unknown"
    # USGS place strings look like "70 km SSW of Town, Country".
    return place.split(", ")[-1].strip() or "Unknown"


def parse_feed(payload: dict) -> list[CrisisEvent]:
    """Map a USGS GeoJSON payload to CrisisEvents (pure, unit-testable)."""
    events: list[CrisisEvent] = []
    for feat in payload.get("features", []):
        try:
            props = feat.get("properties", {})
            lon, lat, *_ = feat.get("geometry", {}).get("coordinates", [None, None])
            mag = props.get("mag")
            if lat is None or lon is None or mag is None:
                continue
            fid = feat.get("id") or f"{lat},{lon},{props.get('time')}"
            events.append(
                normalizer.make_event(
                    id=f"usgs-{fid}",
                    kind="earthquake",
                    title=props.get("title") or f"M{mag} earthquake",
                    lat=float(lat),
                    lon=float(lon),
                    country=_country_from_place(props.get("place", "")),
                    severity=normalizer.normalize_severity_usgs(float(mag)),
                    started_at=normalizer.epoch_ms_to_utc(props["time"]),
                    source=SOURCE,
                    source_url=props.get("url", "https://earthquake.usgs.gov"),
                    raw={"mag": mag, "place": props.get("place")},
                )
            )
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            logger.warning("USGS: skipping malformed feature: %s", exc)
    return events


async def fetch(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    url = os.getenv("USGS_FEED_URL", DEFAULT_FEED)
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        events = parse_feed(resp.json())
        logger.info("USGS: ingested %d earthquake events", len(events))
        return events
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("USGS feed unavailable, skipping cycle: %s", exc)
        return []
    finally:
        if own:
            await client.aclose()
