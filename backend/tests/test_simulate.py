"""Full simulate flow — the Day 2 exit criterion.

POST /simulate must return a complete, schema-valid SimulationResult from
seed data with three grounded options and all three horizons, entirely
offline (no LLM configured -> template fallback path).
"""

import asyncio

from fastapi.testclient import TestClient

from backend.main import app
from backend.models import SimulationResult
from backend.simulation.orchestrator import run_full_simulation
from scripts.seed_events import load_seed_events

client = TestClient(app)
EVENTS = {e.id: e for e in load_seed_events()}


class TestOrchestratorOffline:
    def test_full_result_from_seed_data(self):
        """No LLM available -> templates; result still complete and valid."""
        event = EVENTS["seed-FL-001"]
        result = asyncio.run(
            run_full_simulation(event, horizon="24h", n_runs=2000, seed=42)
        )
        assert isinstance(result, SimulationResult)
        assert set(result.horizons) == {"6h", "24h", "72h"}
        assert len(result.options) == 3
        # Every option's after-range must sit within the 24h baseline.
        base = result.horizons["24h"].exposed_population
        for opt in result.options:
            assert opt.exposed_population_after[1] <= base[1]

    def test_earthquake_event_supported(self):
        event = EVENTS["seed-EQ-004"]
        result = asyncio.run(
            run_full_simulation(event, horizon="6h", n_runs=1500, seed=1)
        )
        assert result.event_id == event.id
        assert result.gpu_metrics.n_runs == 1500

    def test_cache_returns_same_result(self):
        event = EVENTS["seed-FL-001"]
        a = asyncio.run(run_full_simulation(event, horizon="24h", n_runs=2000, seed=7))
        b = asyncio.run(run_full_simulation(event, horizon="24h", n_runs=2000, seed=7))
        assert a.model_dump() == b.model_dump()


class TestSimulateEndpoint:
    def test_post_simulate_returns_valid_result(self):
        r = client.post("/api/events/seed-FL-001/simulate?horizon=24h&runs=2000")
        assert r.status_code == 200
        result = SimulationResult.model_validate(r.json())
        assert len(result.options) == 3
        assert "24h" in result.horizons

    def test_unsupported_kind_returns_422(self):
        # volcano has no Monte Carlo kernel (the ensemble ships flood,
        # quake, cyclone, wildfire).
        r = client.post("/api/events/seed-VO-012/simulate")
        assert r.status_code == 422

    def test_unknown_event_404(self):
        assert client.post("/api/events/nope/simulate").status_code == 404

    def test_bad_horizon_422(self):
        r = client.post("/api/events/seed-FL-001/simulate?horizon=48h")
        assert r.status_code == 422


class TestBriefEndpoint:
    def test_post_brief_returns_valid_briefing(self):
        r = client.post("/api/events/seed-FL-001/brief")
        assert r.status_code == 200
        body = r.json()
        assert body["headline"]
        assert body["confirmed_facts"]
