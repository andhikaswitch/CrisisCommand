"""End-to-end smoke test — a stage is done when this passes through it.

Day 1: seed events load → Monte Carlo runs → forecast JSON validates.
Day 2: full simulate flow → complete SimulationResult with three grounded
policy options (offline template path when no LLM is configured).

Run:  python scripts/smoke_test.py
"""

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.models import HorizonForecast, SimulationResult  # noqa: E402
from backend.simulation.monte_carlo import run_simulation  # noqa: E402
from backend.simulation.orchestrator import run_full_simulation  # noqa: E402
from scripts.seed_events import load_seed_events  # noqa: E402


def main() -> int:
    events = load_seed_events()
    assert len(events) == 15, f"expected 15 seed events, got {len(events)}"
    print(f"[1/4] seed events: {len(events)} loaded, schema-valid")

    jakarta = next(e for e in events if e.id == "seed-FL-001")
    out = run_simulation(jakarta, horizon="24h", n_runs=2000, seed=42)
    print(
        f"[2/4] monte carlo: 2000 runs on {out.metrics.device} "
        f"in {out.metrics.wall_ms:.0f}ms "
        f"({out.metrics.runs_per_sec:,.0f} runs/sec)"
    )

    revalidated = HorizonForecast.model_validate_json(out.forecast.model_dump_json())
    p10, p90 = revalidated.exposed_population
    pop = jakarta.population_context.exposed_estimate
    assert 0 <= p10 <= p90 <= pop, f"insane range ({p10}, {p90}) vs pop {pop}"
    assert p90 > 0, "flood simulation exposed nobody — model broken"
    print(
        f"[3/4] forecast valid: exposed population {p10:,}-{p90:,} "
        f"(p10-p90 of {pop:,} base), confidence={revalidated.confidence}"
    )

    result = asyncio.run(
        run_full_simulation(jakarta, horizon="24h", n_runs=2000, seed=42, use_cache=False)
    )
    result = SimulationResult.model_validate_json(result.model_dump_json())
    assert set(result.horizons) == {"6h", "24h", "72h"}
    assert len(result.options) == 3, "must offer exactly three options"
    base = result.horizons["24h"].exposed_population
    for opt in result.options:
        assert opt.exposed_population_after[1] <= base[1], "invented number leaked"
    names = " | ".join(o.name for o in result.options)
    print(
        f"[4/4] full simulation: 3 grounded options "
        f"(baseline exposed {base[0]:,}-{base[1]:,})\n"
        f"        options: {names}"
    )
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
