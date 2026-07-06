"""Schema contract tests (ARCHITECTURE.md §2)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models import (
    CrisisEvent,
    GeoZone,
    GpuMetrics,
    HorizonForecast,
    PolicyOption,
    PopContext,
    SimulationResult,
)


def _event(**overrides) -> CrisisEvent:
    base = dict(
        id="seed-FL-000",
        kind="flood",
        title="Test flood",
        lat=-6.2,
        lon=106.8,
        country="Indonesia",
        severity=0.5,
        started_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source="SEED",
        source_url="https://example.org",
    )
    base.update(overrides)
    return CrisisEvent(**base)


def _option(**overrides) -> PolicyOption:
    base = dict(
        id="opt-1",
        name="Immediate staged evacuation",
        description="Evacuate zones A-C now.",
        exposed_population_after=(100, 400),
        est_cost_usd=(1_000_000, 5_000_000),
        response_time_hours=6.0,
        tradeoffs=["high upfront cost"],
        affected_zones=[GeoZone(lat=-6.2, lon=106.8, radius_km=10, role="evacuation")],
    )
    base.update(overrides)
    return PolicyOption(**base)


class TestCrisisEvent:
    def test_valid_event_roundtrips(self):
        e = _event()
        assert CrisisEvent.model_validate_json(e.model_dump_json()) == e

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            _event(kind="meteor")

    def test_severity_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            _event(severity=1.5)

    def test_lat_lon_bounds(self):
        with pytest.raises(ValidationError):
            _event(lat=91.0)
        with pytest.raises(ValidationError):
            _event(lon=-181.0)

    def test_naive_datetime_coerced_to_utc(self):
        e = _event(started_at=datetime(2020, 1, 1, 12, 0))
        assert e.started_at.tzinfo is not None
        assert e.started_at.utcoffset().total_seconds() == 0


class TestHorizonForecast:
    def test_p90_below_p10_rejected(self):
        with pytest.raises(ValidationError):
            HorizonForecast(
                exposed_population=(500, 100),
                severity_curve=[0.1],
                confidence="low",
                drivers=["x"],
            )

    def test_severity_curve_bounds_enforced(self):
        with pytest.raises(ValidationError):
            HorizonForecast(
                exposed_population=(100, 500),
                severity_curve=[0.5, 1.2],
                confidence="low",
                drivers=["x"],
            )


class TestPolicyOption:
    def test_valid(self):
        assert _option().response_time_hours == 6.0

    def test_inverted_cost_range_rejected(self):
        with pytest.raises(ValidationError):
            _option(est_cost_usd=(5_000_000, 1_000_000))


class TestSimulationResult:
    def test_exactly_three_options_required(self):
        forecast = HorizonForecast(
            exposed_population=(100, 500),
            severity_curve=[0.2, 0.4],
            confidence="medium",
            drivers=["rainfall"],
        )
        metrics = GpuMetrics(
            device="cpu", n_runs=100, batch_size=100, wall_ms=10.0, runs_per_sec=1e4
        )
        common = dict(
            event_id="seed-FL-000",
            horizons={"24h": forecast},
            gpu_metrics=metrics,
            generated_at=datetime.now(timezone.utc),
        )
        SimulationResult(options=[_option(), _option(), _option()], **common)
        with pytest.raises(ValidationError):
            SimulationResult(options=[_option(), _option()], **common)


class TestPopContext:
    def test_negative_population_rejected(self):
        with pytest.raises(ValidationError):
            PopContext(
                nearest_city="X",
                city_population=-1,
                density_band="high",
                exposed_estimate=10,
            )
