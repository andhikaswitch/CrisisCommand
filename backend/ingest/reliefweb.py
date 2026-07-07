"""ReliefWeb humanitarian disasters ingestor (ARCHITECTURE.md §3).

ReliefWeb's API is free but (since 2025) requires a pre-approved `appname`
requested via https://apidoc.reliefweb.int/parameters#appname. This ingestor
is therefore OPT-IN: it activates only when RELIEFWEB_APPNAME is set, and
the scheduler skips registering it otherwise. Parsing is fully implemented
and unit-tested against a real payload shape, so switching it on is just
the env var.

Mapping: v2 /disasters (status alert|ongoing) → CrisisEvent. Coordinates
come from the primary country centroid (ReliefWeb disasters are country-
scoped); severity maps from status (alert 0.7 > ongoing 0.55) — coarse and
honest, like the GDACS alert-level mapping.
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.ingest import normalizer
from backend.models import CrisisEvent, CrisisKind

logger = logging.getLogger(__name__)

SOURCE = "ReliefWeb"
API = "https://api.reliefweb.int/v2/disasters"
_TIMEOUT = httpx.Timeout(20.0, connect=8.0)

STATUS_SEVERITY = {"alert": 0.7, "ongoing": 0.55}

# ReliefWeb disaster-type names → our kinds; unmapped types are dropped.
TYPE_KIND: dict[str, CrisisKind] = {
    "earthquake": "earthquake",
    "flood": "flood",
    "flash flood": "flood",
    "tropical cyclone": "cyclone",
    "wild fire": "wildfire",
    "drought": "drought",
    "volcano": "volcano",
}


def enabled() -> bool:
    return bool(os.getenv("RELIEFWEB_APPNAME"))


def _kind_of(types: list[dict]) -> CrisisKind | None:
    for t in types or []:
        kind = TYPE_KIND.get((t.get("name") or "").lower())
        if kind:
            return kind
    return None


def parse_feed(payload: dict) -> list[CrisisEvent]:
    """Map a v2 /disasters payload to CrisisEvents (pure, unit-testable)."""
    events: list[CrisisEvent] = []
    for item in payload.get("data", []) or []:
        try:
            fields = item.get("fields", {}) or {}
            kind = _kind_of(fields.get("type", []))
            if kind is None:
                continue
            status = (fields.get("status") or "").lower()
            if status not in STATUS_SEVERITY:
                continue  # past disasters are history, not active events
            country = fields.get("primary_country", {}) or {}
            loc = country.get("location", {}) or {}
            lat, lon = loc.get("lat"), loc.get("lon")
            if lat is None or lon is None:
                continue
            events.append(
                normalizer.make_event(
                    id=f"reliefweb-{item.get('id')}",
                    kind=kind,
                    title=fields.get("name") or f"{kind} — {country.get('name')}",
                    lat=float(lat),
                    lon=float(lon),
                    country=country.get("name", "Unknown"),
                    severity=STATUS_SEVERITY[status],
                    started_at=normalizer.parse_iso_utc(
                        (fields.get("date", {}) or {}).get("created")
                    ),
                    source=SOURCE,
                    source_url=fields.get("url", "https://reliefweb.int"),
                    raw={"status": status},
                )
            )
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("ReliefWeb: skipping malformed item: %s", exc)
    return events


async def fetch(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    appname = os.getenv("RELIEFWEB_APPNAME")
    if not appname:
        logger.info("ReliefWeb disabled (RELIEFWEB_APPNAME not set)")
        return []
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        resp = await client.get(API, params={
            "appname": appname,
            "limit": 50,
            "filter[field]": "status",
            "filter[value][]": ["alert", "ongoing"],
            "filter[operator]": "OR",
            "fields[include][]": [
                "name", "type", "status", "date", "url",
                "primary_country",
            ],
        })
        resp.raise_for_status()
        events = parse_feed(resp.json())
        logger.info("ReliefWeb: ingested %d humanitarian events", len(events))
        return events
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ReliefWeb unavailable, skipping cycle: %s", exc)
        return []
    finally:
        if own:
            await client.aclose()
