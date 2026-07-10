"""News-headline tension signals via GDELT DOC 2.0 (free, no key).

ARCHITECTURE.md §3: "tension" events come from clustered news headlines
only, marked confidence: low, visually distinct on the globe. Scope guard:
news headlines suffice — no social media.

Design: a curated watchlist of documented geopolitical flashpoints (a
region name + coordinates for the marker). Every cycle we ask GDELT for
English articles in the last 24h matching <region> + conflict vocabulary
and treat elevated coverage density as a tension signal:

    severity = 0.2 + 0.45 * (articles / cap)      # capped at 0.65

- Below EMIT_THRESHOLD articles → no signal (quiet regions stay quiet).
- Severity is capped well under the red band: this is signal detection
  from headlines, never a claim that something is happening on the ground.
- Sample headlines ride along in `raw` so the briefing stays traceable.
- GDELT rate limit is 1 request / 5s — requests are spaced accordingly.
- On the AMD GPU host, P3 (PROMPTS.md) classifies items per-headline on
  vLLM; this keyword-cluster path is the offline/local equivalent.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from backend.ingest import normalizer
from backend.models import CrisisEvent

logger = logging.getLogger(__name__)

SOURCE = "GDELT"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# GDELT documents ">=5s between requests" but in practice throttles harder;
# 12s spacing + one retry keeps a 6-region sweep under the 5-min poll budget.
_RATE_SPACING_S = 12.0
_RETRY_AFTER_S = 20.0

VOCAB = "(military OR conflict OR strikes OR clashes OR mobilization)"
MAX_RECORDS = 75
EMIT_THRESHOLD = 15   # articles/24h below this → no signal
SEVERITY_FLOOR = 0.2
SEVERITY_CAP = 0.65   # tension signals never reach the red band


@dataclass(frozen=True)
class Flashpoint:
    name: str
    query: str      # GDELT keyword term for the region
    lat: float
    lon: float
    country: str


# Documented, long-running flashpoints. Marker sits at a representative
# coordinate; the signal is about coverage of the region, not that point.
WATCHLIST: list[Flashpoint] = [
    Flashpoint("Ukraine conflict zone", '"ukraine"', 49.0, 32.0, "Ukraine"),
    Flashpoint("South China Sea", '"south china sea"', 15.2, 117.7, "South China Sea"),
    Flashpoint("Taiwan Strait", '"taiwan strait"', 24.2, 119.5, "Taiwan Strait"),
    Flashpoint("Sudan conflict", '"sudan"', 15.5, 32.56, "Sudan"),
    Flashpoint("Sahel region", '"sahel"', 15.0, 0.0, "Sahel"),
    Flashpoint("Korean Peninsula", '"north korea"', 38.3, 127.0, "Korean Peninsula"),
]


def article_stats(payload: dict) -> tuple[int, list[str]]:
    """(article count, top-3 sample headlines) from a DOC artlist payload."""
    articles = payload.get("articles", []) or []
    titles: list[str] = []
    for a in articles[:3]:
        t = (a.get("title") or "").strip()
        if t:
            titles.append(t[:120])
    return len(articles), titles


def severity_from_count(count: int, cap: int = MAX_RECORDS) -> float:
    return round(min(SEVERITY_CAP, SEVERITY_FLOOR + 0.45 * (count / cap)), 3)


def build_event(fp: Flashpoint, count: int, samples: list[str],
                now: datetime | None = None) -> CrisisEvent:
    now = now or datetime.now(timezone.utc)
    slug = fp.name.lower().replace(" ", "-")
    return normalizer.make_event(
        id=f"tension-{slug}-{now.strftime('%Y%m%d')}",  # stable per day
        kind="tension",
        title=(
            f"Tension signal — {fp.name}: elevated conflict coverage "
            f"({count}+ articles/24h)"
        ),
        lat=fp.lat,
        lon=fp.lon,
        country=fp.country,
        severity=severity_from_count(count),
        started_at=now,
        source=SOURCE,
        source_url="https://www.gdeltproject.org/",
        raw={
            "signal": "news-cluster",
            "article_count_24h": count,
            "sample_headlines": samples,
            "note": "headline-density signal only; confidence low by design",
        },
    )


async def fetch(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    base = os.getenv("GDELT_DOC_API", API)
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    events: list[CrisisEvent] = []
    try:
        for i, fp in enumerate(WATCHLIST):
            if i > 0:
                await asyncio.sleep(_RATE_SPACING_S)
            params = {
                "query": f"{fp.query} {VOCAB} sourcelang:eng",
                "mode": "artlist",
                "format": "json",
                "timespan": "24h",
                "maxrecords": str(MAX_RECORDS),
            }
            try:
                resp = await client.get(base, params=params)
                if resp.status_code == 429:  # throttled: back off once
                    await asyncio.sleep(_RETRY_AFTER_S)
                    resp = await client.get(base, params=params)
                resp.raise_for_status()
                count, samples = article_stats(resp.json())
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("GDELT: %s unavailable, skipping: %s", fp.name, exc)
                continue
            if count >= EMIT_THRESHOLD:
                events.append(build_event(fp, count, samples))
        logger.info("GDELT: %d tension signal(s) above threshold", len(events))
        return events
    finally:
        if own:
            await client.aclose()
