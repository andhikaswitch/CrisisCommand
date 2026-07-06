"""WebSocket hub + simulation progress streaming."""

import asyncio

from fastapi.testclient import TestClient

from backend.main import app
from backend.simulation.orchestrator import PROGRESS_CHUNKS, run_full_simulation
from scripts.seed_events import load_seed_events

client = TestClient(app)
EVENTS = {e.id: e for e in load_seed_events()}


class TestWebSocket:
    def test_connect_receives_gpu_stats(self):
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "gpu_stats"
            assert msg["backend"] in ("gpu", "cpu")

    def test_sim_progress_broadcast_during_simulate(self):
        with client.websocket_connect("/ws") as ws:
            r = client.post("/api/events/seed-FL-001/simulate?horizon=6h&runs=1000")
            assert r.status_code == 200
            # Drain messages until we see monte_carlo progress and complete.
            stages = set()
            runs_seen = []
            for _ in range(40):
                msg = ws.receive_json()
                if msg["type"] != "sim_progress":
                    continue
                stages.add(msg["stage"])
                if msg["stage"] == "monte_carlo":
                    runs_seen.append(msg["runs_done"])
                if msg["stage"] == "complete":
                    break
            assert "monte_carlo" in stages
            assert "complete" in stages
            assert runs_seen == sorted(runs_seen)  # monotonically increasing
            assert runs_seen[-1] == 1000


class TestProgressCallback:
    def test_orchestrator_emits_chunked_progress(self):
        event = EVENTS["seed-FL-001"]
        calls = []
        asyncio.run(
            run_full_simulation(
                event, horizon="24h", n_runs=2000, seed=3, use_cache=False,
                progress_cb=lambda stage, done, total: calls.append((stage, done, total)),
            )
        )
        mc = [(d, t) for s, d, t in calls if s == "monte_carlo"]
        assert len(mc) == PROGRESS_CHUNKS
        assert mc[-1] == (2000, 2000)
        assert [s for s, _, _ in calls][-1] == "complete"
        assert ("scenario_agent", 2000, 2000) in calls


class TestSeverityBand:
    def test_band_present_and_ordered(self):
        from backend.simulation.monte_carlo import run_simulation

        event = EVENTS["seed-FL-001"]
        out = run_simulation(event, "24h", n_runs=1000, force_cpu=True, seed=5)
        f = out.forecast
        assert f.severity_band_low is not None and f.severity_band_high is not None
        assert len(f.severity_band_low) == len(f.severity_curve)
        for lo, mid, hi in zip(f.severity_band_low, f.severity_curve, f.severity_band_high):
            assert lo <= hi
            assert lo - 1e-6 <= mid <= hi + 1e-6

    def test_chunked_equals_shape_and_bounds(self):
        from backend.simulation.monte_carlo import run_simulation

        event = EVENTS["seed-EQ-004"]
        out = run_simulation(
            event, "6h", n_runs=1000, force_cpu=True, seed=5, n_chunks=10
        )
        assert out.exposed.shape == (1000,)
        p10, p90 = out.forecast.exposed_population
        assert 0 <= p10 <= p90
