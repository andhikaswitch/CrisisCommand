"""Core pydantic schemas for CrisisCommand.

These are the data contracts defined in ARCHITECTURE.md §2. Every component
(ingestors, simulation engine, LLM layer, API) speaks these types. Numbers
shown to the user are always ranges (p10, p90) — never single hard values.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CrisisKind = Literal[
    "earthquake", "flood", "cyclone", "wildfire", "volcano", "drought", "tension"
]

Confidence = Literal["low", "medium", "high"]

ZoneRole = Literal["evacuation", "hazard", "staging"]

Horizon = Literal["6h", "24h", "72h"]

HORIZON_HOURS: dict[str, int] = {"6h": 6, "24h": 24, "72h": 72}


class PopContext(BaseModel):
    """Population context near the event — nearest city and density band."""

    nearest_city: str
    city_population: int = Field(ge=0)
    density_band: Literal["low", "medium", "high"]
    # People plausibly within the hazard's reach; the Monte Carlo engine
    # draws exposure fractions against this base, never above it.
    exposed_estimate: int = Field(ge=0)
    notes: str | None = None


class GeoZone(BaseModel):
    """A renderable zone on the globe (policy option overlay)."""

    shape: Literal["circle"] = "circle"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0)
    role: ZoneRole


class CrisisEvent(BaseModel):
    id: str  # source-prefixed, e.g. "gdacs-EQ-123" / "seed-FL-001"
    kind: CrisisKind
    title: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    country: str
    severity: float = Field(ge=0.0, le=1.0)  # normalized 0-1 across sources
    started_at: datetime
    source: str  # "GDACS" | "USGS" | "ReliefWeb" | "News" | "SEED"
    source_url: str
    raw: dict = Field(default_factory=dict)  # original payload, never shown raw
    population_context: PopContext | None = None

    @field_validator("started_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class GpuMetrics(BaseModel):
    """Measured (never estimated) compute metrics for the HUD readout."""

    device: str  # e.g. "AMD Instinct MI300X" or "cpu"
    n_runs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    wall_ms: float = Field(ge=0)
    runs_per_sec: float = Field(ge=0)
    vram_gb: float | None = None
    util_pct: float | None = None


class HorizonForecast(BaseModel):
    exposed_population: tuple[int, int]  # (p10, p90) — never a point estimate
    severity_curve: list[float]  # 0-1 values for the escalation chart
    confidence: Confidence
    drivers: list[str]  # human-readable factors

    @model_validator(mode="after")
    def _sane_range(self) -> "HorizonForecast":
        p10, p90 = self.exposed_population
        if p10 < 0 or p90 < p10:
            raise ValueError("exposed_population must satisfy 0 <= p10 <= p90")
        if any(not (0.0 <= s <= 1.0) for s in self.severity_curve):
            raise ValueError("severity_curve values must be within [0, 1]")
        return self


class PolicyOption(BaseModel):
    id: str
    name: str  # "Immediate staged evacuation"
    description: str
    exposed_population_after: tuple[int, int]
    est_cost_usd: tuple[int, int]
    response_time_hours: float = Field(ge=0)
    tradeoffs: list[str]  # honest cons
    affected_zones: list[GeoZone]

    @model_validator(mode="after")
    def _sane_ranges(self) -> "PolicyOption":
        for lo, hi in (self.exposed_population_after, self.est_cost_usd):
            if lo < 0 or hi < lo:
                raise ValueError("ranges must satisfy 0 <= low <= high")
        return self


class SimulationResult(BaseModel):
    event_id: str
    horizons: dict[Horizon, HorizonForecast]
    options: list[PolicyOption] = Field(min_length=3, max_length=3)
    gpu_metrics: GpuMetrics
    generated_at: datetime


class Briefing(BaseModel):
    """P1 output schema (PROMPTS.md) — the AI situation briefing."""

    headline: str
    summary: str
    confirmed_facts: list[str] = Field(min_length=1)
    key_unknowns: list[str] = Field(min_length=1)
    watch_indicators: list[str] = Field(min_length=1)
