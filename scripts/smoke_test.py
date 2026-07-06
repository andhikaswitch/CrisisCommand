"""End-to-end smoke test — a stage is done when this passes through it.

Day 1 coverage: seed events load → Monte Carlo runs (small batch) → forecast
JSON validates against the schema. Day 2 extends this through the LLM layer
to a full SimulationResult with three policy options.

Run:  python scripts/smoke_test.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.models import HorizonForecast  # noqa: E402
from backend.simulation.monte_carlo import run_simulation  # noqa: E402
from scripts.seed_events import load_seed_events  # noqa: E402


def main() -> int:
    events = load_seed_events()
    assert len(events) == 15, f"expected 15 seed events, got {len(events)}"
    print(f"[1/3] seed events: {len(events)} loaded, schema-valid")

    jakarta = next(e for e in events if e.id == "seed-FL-001")
    out = run_simulation(jakarta, horizon="24h", n_runs=2000, seed=42)
    print(
        f"[2/3] monte carlo: 2000 runs on {out.metrics.device} "
        f"in {out.metrics.wall_ms:.0f}ms "
        f"({out.metrics.runs_per_sec:,.0f} runs/sec)"
    )

    # Round-trip through JSON exactly as the API will serve it.
    revalidated = HorizonForecast.model_validate_json(out.forecast.model_dump_json())
    p10, p90 = revalidated.exposed_population
    pop = jakarta.population_context.exposed_estimate
    assert 0 <= p10 <= p90 <= pop, f"insane range ({p10}, {p90}) vs pop {pop}"
    assert p90 > 0, "flood simulation exposed nobody — model broken"
    print(
        f"[3/3] forecast valid: exposed population {p10:,}-{p90:,} "
        f"(p10-p90 of {pop:,} base), confidence={revalidated.confidence}"
    )
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
