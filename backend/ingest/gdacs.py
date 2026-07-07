"""GDACS multi-hazard ingestor — public GeoJSON event list (ARCHITECTURE.md §3).

Fetch → map each feature to a CrisisEvent → return. GDACS-specific quirks
(alert levels, event-type codes, its dict-shaped url field) are handled here;
severity/kind normalization is shared in normalizer.py. Any failure logs and
returns [] so a flaky feed cannot take the app down (failure mode §8).
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.ingest import normalizer
from backend.models import CrisisEvent

logger = logging.getLogger(__name__)

SOURCE = "GDACS"
DEFAULT_FEED = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


def _report_url(props: dict) -> str:
    url = props.get("url")
    if isinstance(url, dict):  # GDACS sometimes nests {report, details, geometry}
        return url.get("report") or url.get("details") or "https://www.gdacs.org"
    if isinstance(url, str) and url:
        return url
    return "https://www.gdacs.org"


def _float_or_none(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_feed(payload: dict) -> list[CrisisEvent]:
    """Map a GDACS GeoJSON payload to CrisisEvents (pure, unit-testable)."""
    events: list[CrisisEvent] = []
    for feat in payload.get("features", []):
        try:
            props = feat.get("properties", {})
            kind = normalizer.gdacs_kind(props.get("eventtype", ""))
            if kind is None:  # hazard class we don't model — skip
                continue
            coords = feat.get("geometry", {}).get("coordinates") or []
            if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            # GDACS mixes Point events with Polygon overlays for the same
            # event; skip non-Point geometries quietly (the Point carries it).
            if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                continue
            event_id = props.get("eventid") or props.get("eventname") or f"{lat},{lon}"
            score = _float_or_none(props.get("alertscore") or props.get("episodealertscore"))
            title = (
                props.get("htmldescription")
                or props.get("name")
                or props.get("eventname")
                or f"{kind} event"
            )
            events.append(
                normalizer.make_event(
                    id=f"gdacs-{props.get('eventtype')}-{event_id}",
                    kind=kind,
                    title=title,
                    lat=float(lat),
                    lon=float(lon),
                    country=props.get("country", "Unknown"),
                    severity=normalizer.normalize_severity_gdacs(
                        props.get("alertlevel", "Green"), score
                    ),
                    started_at=normalizer.parse_iso_utc(props["fromdate"]),
                    source=SOURCE,
                    source_url=_report_url(props),
                    raw={
                        "eventtype": props.get("eventtype"),
                        "alertlevel": props.get("alertlevel"),
                    },
                )
            )
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            logger.warning("GDACS: skipping malformed feature: %s", exc)
    return events


async def fetch(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    url = os.getenv("GDACS_FEED_URL", DEFAULT_FEED)
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        events = parse_feed(resp.json())
        logger.info("GDACS: ingested %d multi-hazard events", len(events))
        return events
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GDACS feed unavailable, skipping cycle: %s", exc)
        return []
    finally:
        if own:
            await client.aclose()
