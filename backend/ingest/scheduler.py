"""Live ingestion scheduler (LIVE mode only) — ARCHITECTURE.md §3.

Runs the enabled ingestors on a fixed interval, feeds each batch to the
EventStore (which dedups on the GPU), and broadcasts genuinely-new events to
WS clients as `event_new`. Disabled entirely in SEED mode: the demo's safety
net never depends on a scheduler or a live feed.

A single failing feed only skips its own cycle (the ingestor returns []),
so one dead source cannot stop the others or crash the loop.
"""

from __future__ import annotations

import asyncio
import logging

from backend.ingest import bmkg, flood_risk, gdacs, usgs
from backend.ingest.store import EventStore

logger = logging.getLogger(__name__)

POLL_SECONDS = 300  # 5 min (ARCHITECTURE.md §3)

# (source label, async fetch fn). ReliefWeb/news are Day-5 stretch — cut by
# default; seed tension events already cover the tension class. BMKG gives
# official realtime coverage for Indonesia (and exercises cross-feed dedup
# against USGS for the same quakes).
INGESTORS = [
    ("USGS", usgs.fetch),
    ("GDACS", gdacs.fetch),
    ("BMKG", bmkg.fetch),
    # rain-forecast × flood-history signals: national feed for Indonesia,
    # Open-Meteo for the global flood-prone watchlist
    ("BMKG-RAIN", flood_risk.fetch_indonesia),
    ("OPEN-METEO", flood_risk.fetch_global),
]


async def run_cycle(store: EventStore, broadcast=None) -> list:
    """One ingestion pass across all sources. Returns per-source results."""
    results = []
    for source, fetch in INGESTORS:
        try:
            events = await fetch()
            result = store.add_from_source(source, events)
        except Exception as exc:  # defensive: a fetch fn should not raise, but
            logger.exception("ingestor %s crashed", source)
            result = store.add_from_source(source, [], error=str(exc))
            results.append(result)
            continue
        results.append(result)
        if broadcast is not None:
            # Markers drop in live: one event_new per genuinely-new event.
            for e in result.added_events:
                await broadcast({"type": "event_new", "event": e.model_dump(mode="json")})
    return results


async def scheduler_loop(store: EventStore, broadcast=None) -> None:
    """Forever loop; one immediate cycle then every POLL_SECONDS."""
    while True:
        try:
            await run_cycle(store, broadcast)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ingestion cycle failed; continuing")
        await asyncio.sleep(POLL_SECONDS)
