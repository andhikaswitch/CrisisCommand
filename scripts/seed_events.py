"""Curated seed dataset: 15 real, documented historical crisis events.

This is the demo's safety net (`SEED_MODE=true`): the full flow runs offline
with these events, so a dead conference Wi-Fi cannot kill the demo
(ARCHITECTURE.md §3). Every event is public and documented; severity values
are heuristic normalizations (0-1) of documented impact, and population
figures are order-of-magnitude context from public sources — they feed the
Monte Carlo engine as exposure bases, never shown as precise facts.

Kinds covered: flood x4, earthquake x3, cyclone x2, wildfire x2, volcano x1,
drought x1, tension x2 (news-signal class, confidence low by design).

Run directly for a summary table:  python scripts/seed_events.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.models import CrisisEvent, PopContext  # noqa: E402


def _utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


SEED_EVENTS: list[CrisisEvent] = [
    # ---- FLOODS ----------------------------------------------------------
    CrisisEvent(
        id="seed-FL-001",
        kind="flood",
        title="Severe urban flooding across Greater Jakarta",
        lat=-6.2088,
        lon=106.8456,
        country="Indonesia",
        severity=0.75,
        started_at=_utc(2020, 1, 1, 3, 0),
        source="SEED",
        source_url="https://reliefweb.int/disaster/fl-2020-000001-idn",
        raw={"profile": "jakarta-new-year-flood-2020", "displaced_reported": 397000},
        population_context=PopContext(
            nearest_city="Jakarta",
            city_population=10_560_000,
            density_band="high",
            exposed_estimate=400_000,
            notes="Low-lying river basins; ~397k displaced in the documented event.",
        ),
    ),
    CrisisEvent(
        id="seed-FL-009",
        kind="flood",
        title="Monsoon mega-flood across Sindh province",
        lat=26.05,
        lon=68.45,
        country="Pakistan",
        severity=0.9,
        started_at=_utc(2022, 8, 25, 0, 0),
        source="SEED",
        source_url="https://reliefweb.int/disaster/fl-2022-000254-pak",
        raw={"profile": "pakistan-floods-2022"},
        population_context=PopContext(
            nearest_city="Larkana",
            city_population=490_000,
            density_band="medium",
            exposed_estimate=2_000_000,
            notes="Regional slice of the 2022 floods; tens of millions affected nationwide.",
        ),
    ),
    CrisisEvent(
        id="seed-FL-010",
        kind="flood",
        title="Flash flooding in the Ahr valley",
        lat=50.5447,
        lon=7.1130,
        country="Germany",
        severity=0.7,
        started_at=_utc(2021, 7, 14, 18, 0),
        source="SEED",
        source_url="https://en.wikipedia.org/wiki/2021_European_floods",
        raw={"profile": "ahr-valley-flood-2021"},
        population_context=PopContext(
            nearest_city="Bad Neuenahr-Ahrweiler",
            city_population=28_000,
            density_band="medium",
            exposed_estimate=42_000,
            notes="Narrow valley towns; extreme rainfall over saturated ground.",
        ),
    ),
    CrisisEvent(
        id="seed-FL-011",
        kind="flood",
        title="Statewide monsoon flooding in Kerala",
        lat=9.9312,
        lon=76.2673,
        country="India",
        severity=0.8,
        started_at=_utc(2018, 8, 8, 0, 0),
        source="SEED",
        source_url="https://reliefweb.int/disaster/fl-2018-000112-ind",
        raw={"profile": "kerala-floods-2018"},
        population_context=PopContext(
            nearest_city="Kochi",
            city_population=677_000,
            density_band="high",
            exposed_estimate=1_200_000,
            notes="~1.4M displaced statewide in the documented event; dam releases were a driver.",
        ),
    ),
    # ---- EARTHQUAKES -----------------------------------------------------
    CrisisEvent(
        id="seed-EQ-002",
        kind="earthquake",
        title="M9.1 megathrust earthquake off Sumatra (tsunami-genic)",
        lat=3.316,
        lon=95.854,
        country="Indonesia",
        severity=0.98,
        started_at=_utc(2004, 12, 26, 0, 58),
        source="SEED",
        source_url="https://earthquake.usgs.gov/earthquakes/eventpage/official20041226005853450_30",
        raw={"profile": "sumatra-andaman-2004", "magnitude": 9.1},
        population_context=PopContext(
            nearest_city="Banda Aceh",
            city_population=223_000,
            density_band="high",
            exposed_estimate=500_000,
            notes="Coastal exposure dominated; CLAUDE.md's 2004 tsunami region profile.",
        ),
    ),
    CrisisEvent(
        id="seed-EQ-003",
        kind="earthquake",
        title="M7.8 earthquake, southern Türkiye / northern Syria",
        lat=37.226,
        lon=37.014,
        country="Türkiye",
        severity=0.95,
        started_at=_utc(2023, 2, 6, 1, 17),
        source="SEED",
        source_url="https://earthquake.usgs.gov/earthquakes/eventpage/us6000jllz",
        raw={"profile": "turkiye-syria-2023", "magnitude": 7.8},
        population_context=PopContext(
            nearest_city="Gaziantep",
            city_population=2_069_000,
            density_band="high",
            exposed_estimate=1_500_000,
            notes="Dense urban building stock; strong M7.5 aftershock within 9 hours.",
        ),
    ),
    CrisisEvent(
        id="seed-EQ-004",
        kind="earthquake",
        title="M7.8 Gorkha earthquake near Kathmandu",
        lat=28.231,
        lon=84.731,
        country="Nepal",
        severity=0.85,
        started_at=_utc(2015, 4, 25, 6, 11),
        source="SEED",
        source_url="https://earthquake.usgs.gov/earthquakes/eventpage/us20002926",
        raw={"profile": "gorkha-2015", "magnitude": 7.8},
        population_context=PopContext(
            nearest_city="Kathmandu",
            city_population=975_000,
            density_band="high",
            exposed_estimate=800_000,
            notes="Vulnerable masonry stock; major aftershock sequence.",
        ),
    ),
    # ---- CYCLONES --------------------------------------------------------
    CrisisEvent(
        id="seed-CY-005",
        kind="cyclone",
        title="Cyclone Idai landfall near Beira",
        lat=-19.843,
        lon=34.839,
        country="Mozambique",
        severity=0.85,
        started_at=_utc(2019, 3, 14, 22, 0),
        source="SEED",
        source_url="https://reliefweb.int/disaster/tc-2019-000021-moz",
        raw={"profile": "idai-2019"},
        population_context=PopContext(
            nearest_city="Beira",
            city_population=533_000,
            density_band="medium",
            exposed_estimate=600_000,
            notes="Storm surge plus prolonged river flooding after landfall.",
        ),
    ),
    CrisisEvent(
        id="seed-CY-006",
        kind="cyclone",
        title="Super Typhoon Haiyan striking Tacloban",
        lat=11.2444,
        lon=125.0039,
        country="Philippines",
        severity=0.95,
        started_at=_utc(2013, 11, 7, 20, 40),
        source="SEED",
        source_url="https://reliefweb.int/disaster/tc-2013-000139-phl",
        raw={"profile": "haiyan-2013"},
        population_context=PopContext(
            nearest_city="Tacloban",
            city_population=221_000,
            density_band="high",
            exposed_estimate=900_000,
            notes="Record storm surge in a shallow bay; regional exposure across Leyte.",
        ),
    ),
    # ---- WILDFIRES -------------------------------------------------------
    CrisisEvent(
        id="seed-WF-007",
        kind="wildfire",
        title="Black Summer fire complex, NSW south coast",
        lat=-35.71,
        lon=150.18,
        country="Australia",
        severity=0.8,
        started_at=_utc(2019, 12, 30, 5, 0),
        source="SEED",
        source_url="https://en.wikipedia.org/wiki/2019%E2%80%9320_Australian_bushfire_season",
        raw={"profile": "black-summer-2019"},
        population_context=PopContext(
            nearest_city="Batemans Bay",
            city_population=17_000,
            density_band="low",
            exposed_estimate=80_000,
            notes="Holiday-season population surge on the coast; single-road evacuations.",
        ),
    ),
    CrisisEvent(
        id="seed-WF-008",
        kind="wildfire",
        title="Wind-driven wildfire reaching Lahaina",
        lat=20.878,
        lon=-156.681,
        country="United States",
        severity=0.8,
        started_at=_utc(2023, 8, 8, 16, 0),
        source="SEED",
        source_url="https://en.wikipedia.org/wiki/2023_Hawaii_wildfires",
        raw={"profile": "maui-2023"},
        population_context=PopContext(
            nearest_city="Lahaina",
            city_population=12_700,
            density_band="medium",
            exposed_estimate=15_000,
            notes="Hurricane-downslope winds; town-scale exposure, minutes-scale spread.",
        ),
    ),
    # ---- VOLCANO ---------------------------------------------------------
    CrisisEvent(
        id="seed-VO-012",
        kind="volcano",
        title="Mount Merapi major eruptive phase",
        lat=-7.5407,
        lon=110.4457,
        country="Indonesia",
        severity=0.75,
        started_at=_utc(2010, 10, 26, 10, 0),
        source="SEED",
        source_url="https://en.wikipedia.org/wiki/2010_eruptions_of_Mount_Merapi",
        raw={"profile": "merapi-2010"},
        population_context=PopContext(
            nearest_city="Yogyakarta",
            city_population=422_000,
            density_band="high",
            exposed_estimate=350_000,
            notes="~350k evacuated in the documented event; pyroclastic flow corridors.",
        ),
    ),
    # ---- DROUGHT ---------------------------------------------------------
    CrisisEvent(
        id="seed-DR-013",
        kind="drought",
        title="Multi-season drought, Horn of Africa",
        lat=3.114,
        lon=43.65,
        country="Somalia",
        severity=0.8,
        started_at=_utc(2022, 2, 1, 0, 0),
        source="SEED",
        source_url="https://reliefweb.int/disaster/dr-2015-000134-som",
        raw={"profile": "horn-of-africa-drought-2022"},
        population_context=PopContext(
            nearest_city="Baidoa",
            city_population=750_000,
            density_band="medium",
            exposed_estimate=1_500_000,
            notes="Five consecutive failed rains; displacement into urban IDP sites.",
        ),
    ),
    # ---- TENSION SIGNALS (news-cluster class; confidence low by design) --
    CrisisEvent(
        id="seed-TN-014",
        kind="tension",
        title="Border force buildup signals, Eastern Europe",
        lat=50.4501,
        lon=30.5234,
        country="Ukraine",
        severity=0.65,
        started_at=_utc(2022, 1, 24, 12, 0),
        source="SEED",
        source_url="https://en.wikipedia.org/wiki/Prelude_to_the_Russian_invasion_of_Ukraine",
        raw={"profile": "eastern-europe-buildup-2022", "signal_class": "news-cluster"},
        population_context=PopContext(
            nearest_city="Kyiv",
            city_population=2_950_000,
            density_band="high",
            exposed_estimate=2_950_000,
            notes="Signal detection only — clustered public headlines, no prediction claim.",
        ),
    ),
    CrisisEvent(
        id="seed-TN-015",
        kind="tension",
        title="Maritime incident signals, South China Sea",
        lat=15.18,
        lon=117.75,
        country="Philippines (vicinity)",
        severity=0.5,
        started_at=_utc(2023, 10, 22, 8, 0),
        source="SEED",
        source_url="https://en.wikipedia.org/wiki/Territorial_disputes_in_the_South_China_Sea",
        raw={"profile": "scs-signals-2023", "signal_class": "news-cluster"},
        population_context=PopContext(
            nearest_city="Puerto Princesa",
            city_population=307_000,
            density_band="low",
            exposed_estimate=307_000,
            notes="Signal detection only — clustered public headlines, no prediction claim.",
        ),
    ),
]


def load_seed_events() -> list[CrisisEvent]:
    """Return the curated seed events (already schema-validated at import)."""
    return list(SEED_EVENTS)


if __name__ == "__main__":
    events = load_seed_events()
    print(f"{len(events)} seed events loaded and schema-valid\n")
    print(f"{'ID':<13} {'KIND':<11} {'SEV':<5} {'COUNTRY':<22} TITLE")
    for e in events:
        print(f"{e.id:<13} {e.kind:<11} {e.severity:<5} {e.country:<22} {e.title}")
    kinds: dict[str, int] = {}
    for e in events:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    print("\nby kind:", ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
