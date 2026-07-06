"""Full simulation orchestration: Monte Carlo (all horizons) + scenario agent.

Assembles a complete SimulationResult (ARCHITECTURE.md §4) from a seed/live
event: runs the batched Monte Carlo across 6h/24h/72h so the escalation chart
has all horizons, grounds three policy options on the requested horizon's
baseline, and records GPU metrics from that run. Cached per
(event_id, horizon, baseline_hash) — a re-click is instant and spends no
droplet hours.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend import cache
from backend.llm.client import LLMClient
from backend.models import (
    HORIZON_HOURS,
    CrisisEvent,
    Horizon,
    HorizonForecast,
    SimulationResult,
)
from backend.simulation import scenario_agent
from backend.simulation.monte_carlo import (
    DEFAULT_N_RUNS,
    SUPPORTED_KINDS,
    UnsupportedHazardError,
    run_simulation,
)

logger = logging.getLogger(__name__)

_ALL_HORIZONS: list[Horizon] = ["6h", "24h", "72h"]


async def run_full_simulation(
    event: CrisisEvent,
    horizon: Horizon = "24h",
    n_runs: int = DEFAULT_N_RUNS,
    force_cpu: bool = False,
    seed: int | None = None,
    client: LLMClient | None = None,
    use_cache: bool = True,
) -> SimulationResult:
    """Produce a complete, cached SimulationResult for one event/horizon."""
    if event.kind not in SUPPORTED_KINDS:
        raise UnsupportedHazardError(
            f"no Monte Carlo kernel for kind={event.kind!r} yet; "
            f"supported: {SUPPORTED_KINDS}"
        )
    if horizon not in HORIZON_HOURS:
        raise ValueError(f"horizon must be one of {list(HORIZON_HOURS)}")

    # Monte Carlo across all horizons (escalation chart needs the full set).
    forecasts: dict[Horizon, HorizonForecast] = {}
    metrics = None
    for h in _ALL_HORIZONS:
        out = run_simulation(event, horizon=h, n_runs=n_runs, force_cpu=force_cpu, seed=seed)
        forecasts[h] = out.forecast
        if h == horizon:
            metrics = out.metrics
    assert metrics is not None

    baseline = forecasts[horizon].exposed_population
    key = ("sim", event.id, horizon, cache.baseline_hash(*baseline))
    if use_cache:
        cached = cache.get(key, SimulationResult)
        if cached is not None:
            logger.info("simulation cache hit for %s/%s", event.id, horizon)
            return cached

    options = await scenario_agent.generate_options(
        event, forecasts[horizon], horizon, n_runs, client=client
    )

    result = SimulationResult(
        event_id=event.id,
        horizons=forecasts,
        options=options,
        gpu_metrics=metrics,
        generated_at=datetime.now(timezone.utc),
    )
    if use_cache:
        cache.put(key, result)
    return result
