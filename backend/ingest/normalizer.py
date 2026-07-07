"""Shared ingestion logic: severity normalization + kind mapping.

Every ingestor maps its source's quirks locally, then calls the helpers here
to emit a schema-valid CrisisEvent (ARCHITECTURE.md §3). The severity scale
must be comparable across sources, so all normalization lives in one place.

Honesty rule (CLAUDE.md): live events carry NO population_context — we have
no curated exposure figure for them, and inventing one would be fake
precision. The UI gates simulation on population_context being present, so a
live event without it shows as a marker/briefing but is not simulated.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.models import CrisisEvent, CrisisKind

# GDACS event-type code -> our kind. Types we don't model are dropped.
GDACS_KIND: dict[str, CrisisKind] = {
    "EQ": "earthquake",
    "TC": "cyclone",
    "FL": "flood",
    "DR": "drought",
    "VO": "volcano",
    "WF": "wildfire",
}

# GDACS alert level -> baseline severity (0-1). Red/Orange/Green is the
# feed's own triage; we map it onto our shared scale.
GDACS_ALERT_SEVERITY: dict[str, float] = {
    "Red": 0.85,
    "Orange": 0.65,
    "Green": 0.40,
}


def normalize_severity_usgs(magnitude: float) -> float:
    """Earthquake magnitude -> 0-1 severity.

    Linear on the moment-magnitude scale over the range that matters for
    response: M3 ~ 0.05 (minor) to M9 ~ 1.0 (megathrust). Coarse by design.
    """
    return _clamp((magnitude - 3.0) / 6.0, 0.05, 1.0)


def normalize_severity_gdacs(
    alert_level: str, alert_score: float | None = None
) -> float:
    """GDACS alert level (+ optional 0-3 score) -> 0-1 severity."""
    base = GDACS_ALERT_SEVERITY.get(alert_level, 0.4)
    if alert_score is not None:
        # Nudge within the band using the finer 0-3 episode score.
        base = _clamp(0.35 + (alert_score / 3.0) * 0.6, 0.05, 1.0)
    return round(base, 3)


def gdacs_kind(event_type: str) -> CrisisKind | None:
    return GDACS_KIND.get((event_type or "").upper())


def epoch_ms_to_utc(ms: int | float) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def parse_iso_utc(value: str) -> datetime:
    """Parse an ISO-8601 string to aware UTC, tolerating a trailing 'Z'."""
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def make_event(
    *,
    id: str,
    kind: CrisisKind,
    title: str,
    lat: float,
    lon: float,
    country: str,
    severity: float,
    started_at: datetime,
    source: str,
    source_url: str,
    raw: dict,
) -> CrisisEvent:
    """Construct a validated CrisisEvent (population_context intentionally None)."""
    return CrisisEvent(
        id=id,
        kind=kind,
        title=title[:200].strip(),
        lat=lat,
        lon=lon,
        country=country or "Unknown",
        severity=_clamp(severity, 0.0, 1.0),
        started_at=started_at,
        source=source,
        source_url=source_url,
        raw=raw,
        population_context=None,
    )


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
