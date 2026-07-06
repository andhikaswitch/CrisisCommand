"""Monte Carlo engine tests: tensor shapes, statistical bounds, determinism.

Small run counts (500-2000) keep the suite fast on CPU; the model's
statistical properties already hold at that scale.
"""

import pytest
import torch

from backend.simulation.monte_carlo import (
    N_STEPS,
    SUPPORTED_KINDS,
    UnsupportedHazardError,
    _earthquake_kernel,
    _flood_kernel,
    get_device,
    run_simulation,
)
from scripts.seed_events import load_seed_events

EVENTS = {e.id: e for e in load_seed_events()}
JAKARTA_FLOOD = EVENTS["seed-FL-001"]
NEPAL_QUAKE = EVENTS["seed-EQ-004"]


def _gen(seed: int = 7) -> torch.Generator:
    g = torch.Generator(device="cpu")
    g.manual_seed(seed)
    return g


class TestKernelShapesAndBounds:
    @pytest.mark.parametrize("kernel", [_flood_kernel, _earthquake_kernel])
    @pytest.mark.parametrize("hours", [6, 24, 72])
    def test_shape_is_runs_by_steps(self, kernel, hours):
        h = kernel(0.7, hours, 500, _gen(), torch.device("cpu"))
        assert h.shape == (500, N_STEPS)

    @pytest.mark.parametrize("kernel", [_flood_kernel, _earthquake_kernel])
    def test_hazard_within_unit_interval(self, kernel):
        h = kernel(0.9, 24, 1000, _gen(), torch.device("cpu"))
        assert torch.all(h >= 0.0) and torch.all(h < 1.0)

    @pytest.mark.parametrize("kernel", [_flood_kernel, _earthquake_kernel])
    def test_higher_severity_means_more_hazard(self, kernel):
        low = kernel(0.2, 24, 2000, _gen(1), torch.device("cpu")).mean()
        high = kernel(0.9, 24, 2000, _gen(1), torch.device("cpu")).mean()
        assert high > low

    def test_earthquake_starts_hot_flood_builds_up(self):
        """Kind-specific dynamics: quake hazard peaks early, flood accumulates."""
        quake = _earthquake_kernel(0.8, 24, 2000, _gen(), torch.device("cpu")).mean(0)
        flood = _flood_kernel(0.8, 24, 2000, _gen(), torch.device("cpu")).mean(0)
        assert quake[0] > flood[0]
        assert flood.argmax() > 0


class TestRunSimulation:
    def test_forecast_ranges_are_sane(self):
        out = run_simulation(JAKARTA_FLOOD, "24h", n_runs=2000, force_cpu=True, seed=42)
        p10, p90 = out.forecast.exposed_population
        pop = JAKARTA_FLOOD.population_context.exposed_estimate
        assert 0 <= p10 <= p90 <= pop
        assert p90 > 0, "a severity-0.75 urban flood must expose someone"

    def test_exposed_tensor_shape_and_bounds(self):
        out = run_simulation(NEPAL_QUAKE, "24h", n_runs=1500, force_cpu=True, seed=1)
        pop = NEPAL_QUAKE.population_context.exposed_estimate
        assert out.exposed.shape == (1500,)
        assert torch.all(out.exposed >= 0)
        assert torch.all(out.exposed <= pop)

    def test_severity_curve_length_and_bounds(self):
        out = run_simulation(JAKARTA_FLOOD, "6h", n_runs=500, force_cpu=True, seed=3)
        curve = out.forecast.severity_curve
        assert len(curve) == N_STEPS
        assert all(0.0 <= s <= 1.0 for s in curve)

    def test_deterministic_with_seed(self):
        a = run_simulation(JAKARTA_FLOOD, "24h", n_runs=800, force_cpu=True, seed=99)
        b = run_simulation(JAKARTA_FLOOD, "24h", n_runs=800, force_cpu=True, seed=99)
        assert a.forecast.exposed_population == b.forecast.exposed_population
        assert a.forecast.severity_curve == b.forecast.severity_curve

    def test_confidence_degrades_with_horizon(self):
        by_h = {
            h: run_simulation(JAKARTA_FLOOD, h, n_runs=200, force_cpu=True, seed=5)
            for h in ("6h", "24h", "72h")
        }
        assert by_h["6h"].forecast.confidence == "high"
        assert by_h["24h"].forecast.confidence == "medium"
        assert by_h["72h"].forecast.confidence == "low"

    def test_gpu_metrics_recorded(self):
        out = run_simulation(JAKARTA_FLOOD, "24h", n_runs=1000, force_cpu=True)
        m = out.metrics
        assert m.device == "cpu"
        assert m.n_runs == m.batch_size == 1000
        assert m.wall_ms > 0 and m.runs_per_sec > 0

    def test_unsupported_kind_raises(self):
        cyclone = EVENTS["seed-CY-005"]
        assert cyclone.kind not in SUPPORTED_KINDS
        with pytest.raises(UnsupportedHazardError):
            run_simulation(cyclone, "24h", n_runs=100, force_cpu=True)

    def test_bad_horizon_raises(self):
        with pytest.raises(ValueError):
            run_simulation(JAKARTA_FLOOD, "48h", n_runs=100, force_cpu=True)


@pytest.mark.gpu
class TestGpu:
    def test_runs_on_gpu_with_vram_metrics(self):
        if not torch.cuda.is_available():
            pytest.skip("no CUDA/ROCm device")
        assert get_device().type == "cuda"
        out = run_simulation(JAKARTA_FLOOD, "24h", n_runs=10_000, seed=42)
        assert out.metrics.device != "cpu"
        assert out.metrics.vram_gb is not None
