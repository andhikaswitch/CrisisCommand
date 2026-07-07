"""Rain-driven flood-risk signals: weather forecast × documented flood history.

The user-story: "the forecast says heavy rain over Bogor (or Dhaka, or
Mumbai) — that place floods easily — warn me." We combine official/open
weather forecast APIs with a curated table of chronically flood-prone
regions (documented recurring-flood history) and emit a low-severity
`flood` signal event when forecast rainfall over the next 24h crosses a
risk threshold for that region.

Two providers, worldwide coverage:
- Indonesia: BMKG public forecast API (the national met agency — official)
- Global watchlist: Open-Meteo (free, open, no key — fits the no-paid-APIs
  rule), one batched call for all watched cities

Honesty rules (CLAUDE.md — forecasting a WEATHER-DRIVEN hazard from
official feeds is explicitly allowed by the scope guard):
- We invent no meteorology: rainfall numbers come from the providers verbatim.
- The flood-propensity weights are curated, commented, and heuristic — they
  scale the forecast rainfall signal, they never fabricate one.
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

SOURCE_ID = "BMKG-RAIN"      # Indonesian national forecast — its own dot
SOURCE_GLOBAL = "OPEN-METEO"  # global watchlist forecast — its own dot
API = "https://api.bmkg.go.id/publik/prakiraan-cuaca"
API_GLOBAL = "https://api.open-meteo.com/v1/forecast"
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
    adm4: str          # BMKG kelurahan code (Indonesian regions; "" for global)
    lat: float
    lon: float
    propensity: float  # 0-1 documented flood-proneness (heuristic weights)
    note: str
    country: str = "Indonesia"


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

# Global watchlist: chronically flood-prone cities with documented recurring
# floods (monsoon basins, deltas, subsiding coasts). Rainfall via Open-Meteo.
GLOBAL_FLOOD_PRONE: list[Region] = [
    Region("Dhaka", "", 23.81, 90.41, 0.9,
           "GBM delta; monsoon floods most years", "Bangladesh"),
    Region("Mumbai", "", 19.07, 72.87, 0.85,
           "Mithi river + reclaimed lowlands; 2005/2017/2021 deluges", "India"),
    Region("Chennai", "", 13.08, 80.27, 0.8,
           "Adyar/Cooum basins; 2015/2023 major floods", "India"),
    Region("Manila", "", 14.60, 120.98, 0.85,
           "Marikina/Pasig basins; habagat + typhoon floods", "Philippines"),
    Region("Karachi", "", 24.86, 67.01, 0.8,
           "nullah drainage collapse; 2020/2022 urban floods", "Pakistan"),
    Region("Lagos", "", 6.52, 3.38, 0.8,
           "lagoon coast + drainage deficit; annual floods", "Nigeria"),
    Region("Ho Chi Minh City", "", 10.82, 106.63, 0.8,
           "Saigon river delta + subsidence; tidal + rain floods", "Vietnam"),
    Region("Bangkok", "", 13.76, 100.50, 0.75,
           "Chao Phraya delta; 2011 great flood", "Thailand"),
    Region("Houston", "", 29.76, -95.37, 0.7,
           "bayou flash flooding; Harvey 2017", "United States"),
    Region("Guangzhou", "", 23.13, 113.26, 0.75,
           "Pearl River delta; plum-rain + typhoon floods", "China"),
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
                now: datetime | None = None, source: str = SOURCE_ID,
                source_url: str = "https://www.bmkg.go.id/cuaca/prakiraan-cuaca.bmkg",
                ) -> CrisisEvent:
    now = now or datetime.now(timezone.utc)
    slug = region.adm4 or region.name.lower().replace(" ", "-")
    return normalizer.make_event(
        # stable per region+day: repeated polls update, not duplicate
        id=f"rainrisk-{slug}-{now.strftime('%Y%m%d')}",
        kind="flood",
        title=(
            f"Flood risk signal (forecast) — {region.name}: "
            f"{total:.0f}mm rain expected in 24h"
        ),
        lat=region.lat,
        lon=region.lon,
        country=region.country,
        severity=min(risk, SEVERITY_CAP),
        started_at=now,
        source=source,
        source_url=source_url,
        raw={
            "signal": "forecast",
            "rain_24h_mm": round(total, 1),
            "rain_peak_3h_mm": round(peak, 1),
            "flood_propensity": region.propensity,
            "propensity_note": region.note,
        },
    )


def rain_totals_openmeteo(result: dict, now: datetime | None = None) -> tuple[float, float]:
    """(total mm next 24h, peak 3h rolling sum) from one Open-Meteo result."""
    now = now or datetime.now(timezone.utc)
    hourly = result.get("hourly", {}) or {}
    times = hourly.get("time", []) or []
    precip = hourly.get("precipitation", []) or []
    in_window: list[float] = []
    for t, p in zip(times, precip):
        try:
            when = normalizer.parse_iso_utc(t)
            hours_ahead = (when - now).total_seconds() / 3600.0
        except ValueError:
            continue
        if 0 <= hours_ahead <= 24:
            in_window.append(float(p or 0.0))
    total = sum(in_window)
    peak = max(
        (sum(in_window[i : i + 3]) for i in range(max(1, len(in_window) - 2))),
        default=0.0,
    )
    return total, peak


async def fetch_indonesia(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    """BMKG forecasts for the Indonesian watchlist; emit above-threshold signals."""
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
        logger.info("flood-risk ID: %d signal(s) above threshold", len(events))
        return events
    finally:
        if own:
            await client.aclose()


async def fetch_global(client: httpx.AsyncClient | None = None) -> list[CrisisEvent]:
    """Open-Meteo forecasts for the global watchlist — ONE batched request."""
    base = os.getenv("OPEN_METEO_API", API_GLOBAL)
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    events: list[CrisisEvent] = []
    try:
        params = {
            "latitude": ",".join(str(r.lat) for r in GLOBAL_FLOOD_PRONE),
            "longitude": ",".join(str(r.lon) for r in GLOBAL_FLOOD_PRONE),
            "hourly": "precipitation",
            "forecast_days": 2,
            "timezone": "UTC",
        }
        try:
            resp = await client.get(base, params=params)
            resp.raise_for_status()
            results = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("flood-risk global: Open-Meteo unavailable: %s", exc)
            return []
        if isinstance(results, dict):  # single-location responses arrive bare
            results = [results]
        for region, result in zip(GLOBAL_FLOOD_PRONE, results):
            total, peak = rain_totals_openmeteo(result)
            risk = risk_score(total, peak, region.propensity)
            if risk >= RISK_THRESHOLD:
                events.append(build_event(
                    region, total, peak, risk,
                    source=SOURCE_GLOBAL, source_url="https://open-meteo.com/",
                ))
        logger.info("flood-risk global: %d signal(s) above threshold", len(events))
        return events
    finally:
        if own:
            await client.aclose()


# Backwards-compatible alias (scheduler registered the Indonesian fetch first).
fetch = fetch_indonesia
