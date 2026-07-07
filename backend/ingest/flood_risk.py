"""Rain-driven flood-risk signals: BMKG forecast × documented flood history.

The user-story: "BMKG says heavy rain over Bogor on Thursday — Bogor floods
easily — warn me." We combine the OFFICIAL BMKG public weather forecast API
(precipitation, mm per 3h window) with a small curated table of chronically
flood-prone Indonesian regions (documented recurring-flood history), and emit
a low-severity `flood` signal event when forecast rainfall over the next 24h
crosses a risk threshold for that region.

Honesty rules (CLAUDE.md — this is forecasting a WEATHER-DRIVEN hazard from
an official feed, which the scope guard explicitly allows):
- We invent no meteorology: rainfall numbers come from BMKG verbatim.
- The flood-propensity weights are curated, commented, and heuristic — they
  scale the official rainfall signal, they never fabricate one.
- Emitted events are titled "Flood risk signal (forecast)" and capped at
  severity 0.75: a forecast signal, never presented as an occurring flood.
- No rain in the forecast → no events. An empty result is the honest normal.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from backend.ingest import normalizer
from backend.models import CrisisEvent

logger = logging.getLogger(__name__)

SOURCE = "BMKG-RAIN"  # its own freshness dot — distinct from the quake feed
API = "https://api.bmkg.go.id/publik/prakiraan-cuaca"
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)

# Rainfall anchors (mm) for the risk score. Indonesian met practice labels
# >50mm/day "heavy" and >100mm/day "very heavy"; 24h totals near 80mm over
# a poorly-drained basin are a recognized flood setup. Heuristic, commented.
RAIN_24H_REF_MM = 80.0
RAIN_3H_REF_MM = 30.0  # flash-flood style burst
RISK_THRESHOLD = 0.35  # below this we emit nothing
SEVERITY_CAP = 0.75    # a forecast signal never reads as a red occurring event


@dataclass(frozen=True)
class Region:
    name: str
    adm4: str          # representative BMKG kelurahan code for the city
    lat: float
    lon: float
    propensity: float  # 0-1 documented flood-proneness (heuristic weights)
    note: str


# Chronically flood-prone regions (documented recurring floods; weights are
# heuristic rankings of that history, not measurements).
FLOOD_PRONE_REGIONS: list[Region] = [
    Region("Kota Bogor", "32.71.01.1001", -6.62, 106.81, 0.85,
           "upstream Ciliwung basin; recurring urban floods + drives Jakarta floods"),
    Region("Kota Bekasi", "32.75.01.1001", -6.24, 106.99, 0.85,
           "Kali Bekasi overflow; major floods 2020, 2021, 2025"),
    Region("Jakarta Utara", "31.72.01.1001", -6.14, 106.87, 0.9,
           "coastal + land subsidence; chronic rob and rain flooding"),
    Region("Jakarta Pusat", "31.71.01.1001", -6.18, 106.83, 0.8,
           "Ciliwung floodplain; 2007/2013/2020 major floods"),
    Region("Kota Bandung", "32.73.01.1001", -6.91, 107.61, 0.7,
           "Citarum upper basin; Dayeuhkolot-area recurring floods"),
    Region("Kota Semarang", "33.74.01.1001", -6.97, 110.42, 0.8,
           "coastal subsidence + Banjir Kanal; chronic flooding"),
]


def _iter_forecast_entries(payload: dict):
    for block in payload.get("data", []) or []:
        for group in block.get("cuaca", []) or []:
            for entry in group or []:
                yield entry


def rain_totals(payload: dict, now: datetime | None = None) -> tuple[float, float]:
    """(total mm next 24h, max mm in any 3h window) from a forecast payload."""
    now = now or datetime.now(timezone.utc)
    total = 0.0
    peak = 0.0
    for entry in _iter_forecast_entries(payload):
        try:
            when = normalizer.parse_iso_utc(entry["datetime"])
            tp = float(entry.get("tp") or 0.0)
        except (KeyError, ValueError, TypeError):
            continue
        hours_ahead = (when - now).total_seconds() / 3600.0
        if 0 <= hours_ahead <= 24:
            total += tp
            peak = max(peak, tp)
    return total, peak


def risk_score(total_24h_mm: float, peak_3h_mm: float, propensity: float) -> float:
    """Blend sustained and burst rainfall, scaled by documented propensity."""
    sustained = min(1.0, total_24h_mm / RAIN_24H_REF_MM)
    burst = min(1.0, peak_3h_mm / RAIN_3H_REF_MM)
    rain = max(sustained, 0.7 * burst + 0.3 * sustained)
    return round(rain * propensity, 3)


def build_event(region: Region, total: float, peak: float, risk: float,
                now: datetime | None = None) -> CrisisEvent:
    now = now or datetime.now(timezone.utc)
    return normalizer.make_event(
        # stable per region+day: repeated polls update, not duplicate
        id=f"bmkgrain-{region.adm4}-{now.strftime('%Y%m%d')}",
        kind="flood",
        title=(
            f"Flood risk signal (forecast) — {region.name}: "
            f"{total:.0f}mm rain expected in 24h"
        ),
        lat=region.lat,
        lon=region.lon,
        country="Indonesia",
        severity=min(risk, SEVERITY_CAP),
        started_at=now,
        source=SOURCE,
        source_url="https://www.bmkg.go.id/cuaca/prakiraan-cuaca.bmkg",
        raw={
            "signal": "forecast",
            "rain_24h_mm": round(total, 1),
            "rain_peak_3h_mm": round(peak, 1),
            "flood_propensity": region.propensity,
            "propensity_note": region.note,
        },
    )


async def fetch(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    """Poll forecasts for all watched regions; emit above-threshold signals."""
    base = os.getenv("BMKG_WEATHER_API", API)
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    events: list[CrisisEvent] = []
    try:
        for region in FLOOD_PRONE_REGIONS:
            try:
                resp = await client.get(base, params={"adm4": region.adm4})
                resp.raise_for_status()
                total, peak = rain_totals(resp.json())
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("flood-risk: %s forecast unavailable: %s",
                               region.name, exc)
                continue
            risk = risk_score(total, peak, region.propensity)
            if risk >= RISK_THRESHOLD:
                events.append(build_event(region, total, peak, risk))
        logger.info("flood-risk: %d signal(s) above threshold", len(events))
        return events
    finally:
        if own:
            await client.aclose()
