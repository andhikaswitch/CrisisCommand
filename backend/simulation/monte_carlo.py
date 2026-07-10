"""GPU Monte Carlo hazard-exposure engine (PyTorch / ROCm).

The quantitative heart of CrisisCommand (ARCHITECTURE.md §4.1). For a given
event and horizon it runs N stochastic simulations of hazard evolution x
population exposure as ONE batched tensor computation — no Python loops over
runs — and reduces to a p10/p90 exposed-population band plus a mean severity
curve for the escalation chart.

Model honesty: these are simplified, defensible hazard models. Every
parameter and assumption is documented inline; outputs are ranges with a
confidence label, never point estimates. The LLM layer downstream may only
do arithmetic on these numbers (PROMPTS.md rule).

# ROCM: device string is "cuda" — ROCm presents through the CUDA API, so
# this file stays device-agnostic and runs unchanged on any Instinct card or NVIDIA.

CLI (the Day 1 exit check):
    python -m backend.simulation.monte_carlo --runs 10000 [--cpu]
        [--event seed-FL-001] [--horizon 24h] [--seed 42]
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass

import torch

from backend.device import device_label
from backend.models import (
    HORIZON_HOURS,
    Confidence,
    CrisisEvent,
    GpuMetrics,
    HorizonForecast,
)

logger = logging.getLogger(__name__)

DEFAULT_N_RUNS = 10_000
# Time resolution of the hazard curve: fixed step count over any horizon so
# the escalation chart always has the same density.
N_STEPS = 48

# How strongly urban density amplifies the exposed fraction of the base
# population. Heuristic bands; sources are coarse by design.
DENSITY_MULTIPLIER = {"low": 0.6, "medium": 0.8, "high": 1.0}

# No hazard can plausibly expose more than this fraction of the context
# population in-model; keeps tails physical.
MAX_EXPOSURE_FRAC = 0.95

SUPPORTED_KINDS = ("flood", "earthquake", "cyclone", "wildfire")


class UnsupportedHazardError(ValueError):
    """Raised for kinds without a kernel (volcano, drought, tension)."""


@dataclass
class SimulationOutput:
    forecast: HorizonForecast
    metrics: GpuMetrics
    # Raw per-run exposed population, kept for tests and calibration.
    exposed: torch.Tensor


def get_device(force_cpu: bool = False) -> torch.device:
    if force_cpu or not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device("cuda")


def _device_name(device: torch.device) -> str:
    if device.type == "cuda":
        return device_label(device.index or 0)
    return "cpu"


def _lognormal(
    mean: float, sigma: float, n: int, gen: torch.Generator, device: torch.device
) -> torch.Tensor:
    """Lognormal with multiplicative median `mean` — generator-seedable."""
    z = torch.randn(n, generator=gen, device=device)
    return mean * torch.exp(sigma * z)


def _uniform(
    lo: float, hi: float, n: int, gen: torch.Generator, device: torch.device
) -> torch.Tensor:
    return lo + (hi - lo) * torch.rand(n, generator=gen, device=device)


def _flood_kernel(
    severity: float,
    hours: int,
    n_runs: int,
    gen: torch.Generator,
    device: torch.device,
) -> torch.Tensor:
    """Flood hazard curve, shape [n_runs, N_STEPS], values in [0, 1).

    Model: rainfall forcing decays over the storm's lifetime; drainage
    removes water at a stochastic constant rate; ponded water accumulates
    (cumulative sum, floored at zero via monotone envelope) and hazard
    saturates with water depth. Assumptions:
      - rain intensity ~ lognormal around the event severity (heavy tail
        for cloudburst runs)
      - storm duration tau ~ U(0.35, 0.9) of the horizon
      - drainage capacity ~ U(0.15, 0.55) of median forcing — poorer
        drainage in the bad runs is what drives the p90 tail
    """
    dt = hours / N_STEPS
    t = torch.arange(N_STEPS, device=device, dtype=torch.float32) * dt  # [T]

    rain0 = _lognormal(severity, 0.35, n_runs, gen, device).unsqueeze(1)  # [N,1]
    tau = (_uniform(0.35, 0.9, n_runs, gen, device) * hours).unsqueeze(1)  # [N,1]
    drainage = (_uniform(0.15, 0.55, n_runs, gen, device) * severity).unsqueeze(1)

    rain = rain0 * torch.exp(-t.unsqueeze(0) / tau)  # [N,T]
    net_inflow = (rain - drainage) * dt
    water = torch.cumsum(net_inflow, dim=1)
    # Water level cannot go negative once drained; running max of the
    # zero-floored series keeps the peak, cummin-free and fully batched.
    water = torch.clamp(water, min=0.0)

    # Hazard saturates with depth: 1 - exp(-w / w_ref). Accumulated water
    # scales ~ severity x hours, so w_ref must scale with the horizon too;
    # 0.2*hours anchors a median severity-0.75 storm near peak hazard ~0.65
    # with the stochastic tails spread on both sides (not pinned at 1).
    # Ceiling below 1.0: exp() underflows to 0 in float32 for extreme runs,
    # and hazard=1.0 (everyone exposed) is not physical in-model anyway.
    w_ref = 0.2 * hours
    return torch.clamp(1.0 - torch.exp(-water / w_ref), max=0.999)


def _earthquake_kernel(
    severity: float,
    hours: int,
    n_runs: int,
    gen: torch.Generator,
    device: torch.device,
) -> torch.Tensor:
    """Earthquake hazard curve, shape [n_runs, N_STEPS], values in [0, 1).

    Model: exposure is dominated by the mainshock at t=0 and decays as
    search/self-evacuation proceeds, while an Omori-law aftershock term
    (rate ~ K/(t+c)^p) adds renewed exposure. Assumptions:
      - mainshock intensity ~ severity x lognormal(sigma=0.15)
      - building vulnerability factor ~ U(0.55, 1.0) per run (stock quality
        is the dominant unknown)
      - Omori p=1.1, c=0.5h; K scales with severity and its own lognormal
    """
    dt = hours / N_STEPS
    t = torch.arange(N_STEPS, device=device, dtype=torch.float32) * dt  # [T]

    main = _lognormal(severity, 0.15, n_runs, gen, device).clamp(max=1.2)
    vulnerability = _uniform(0.55, 1.0, n_runs, gen, device)
    shock = (main * vulnerability).unsqueeze(1)  # [N,1]

    # Exposure relief: people move out of collapsed/at-risk structures over
    # ~36h characteristic time.
    relief = torch.exp(-t.unsqueeze(0) / 36.0)  # [1,T]

    k = _lognormal(0.25 * severity, 0.4, n_runs, gen, device).unsqueeze(1)  # [N,1]
    omori_rate = k / (t.unsqueeze(0) + 0.5) ** 1.1  # [N,T]
    aftershock = torch.cumsum(omori_rate * dt, dim=1) * 0.3

    return torch.clamp(shock * relief + aftershock, min=0.0, max=0.999)


def _cyclone_kernel(
    severity: float,
    hours: int,
    n_runs: int,
    gen: torch.Generator,
    device: torch.device,
) -> torch.Tensor:
    """Cyclone hazard curve, shape [n_runs, N_STEPS], values in [0, 1).

    Model: a wind-field peak sweeps past (track-cone uncertainty decides how
    directly it hits), followed by a slower rain/surge flood tail.
    Assumptions:
      - storm intensity ~ severity x lognormal(sigma=0.25), capped
      - closest approach time ~ U(0.15, 0.6) of the horizon; wind envelope
        is gaussian around it with width ~ U(0.08, 0.2) of the horizon
      - track offset ~ N(0, 0.75): the cone — many runs are near-misses,
        exp(-offset^2) discounts them (this drives the p10/p90 spread;
        day-ahead track errors are routinely ~100km+, so the cone is wide)
      - post-landfall flood tail: 35% of intensity, decaying over ~24h
    """
    dt = hours / N_STEPS
    t = torch.arange(N_STEPS, device=device, dtype=torch.float32) * dt  # [T]

    intensity = _lognormal(severity, 0.25, n_runs, gen, device).clamp(max=1.2)
    peak_t = (_uniform(0.15, 0.6, n_runs, gen, device) * hours).unsqueeze(1)
    width = (_uniform(0.08, 0.2, n_runs, gen, device) * hours).unsqueeze(1)
    offset = torch.randn(n_runs, generator=gen, device=device) * 0.75
    hit = torch.exp(-offset**2).unsqueeze(1)  # [N,1] track-cone discount
    amp = (intensity.unsqueeze(1) * hit)  # [N,1]

    wind = amp * torch.exp(-(((t.unsqueeze(0) - peak_t) / width) ** 2))
    # rain/surge tail after closest approach, slower decay
    after = torch.clamp(t.unsqueeze(0) - peak_t, min=0.0)
    tail = 0.35 * amp * (1.0 - torch.exp(-after / 6.0)) * torch.exp(-after / 24.0)
    return torch.clamp(wind + tail, min=0.0, max=0.999)


def _wildfire_kernel(
    severity: float,
    hours: int,
    n_runs: int,
    gen: torch.Generator,
    device: torch.device,
) -> torch.Tensor:
    """Wildfire hazard curve, shape [n_runs, N_STEPS], values in [0, 1).

    Model: fire-front growth ~ spread rate x wind, saturating logistically
    as containment takes hold. Assumptions:
      - wind factor ~ lognormal(sigma=0.3) around 1 — the dominant unknown
        (downslope wind events are the catastrophic tail)
      - growth midpoint ~ U(0.25, 0.65) of horizon; steepness scales with
        wind x severity
      - containment ceiling ~ U(0.45, 1.0): how much of the exposure base
        the burn can plausibly reach before lines hold
    """
    dt = hours / N_STEPS
    t = torch.arange(N_STEPS, device=device, dtype=torch.float32) * dt  # [T]

    wind = _lognormal(1.0, 0.3, n_runs, gen, device).clamp(max=2.5)
    ceiling = (_uniform(0.45, 1.0, n_runs, gen, device) * severity).unsqueeze(1)
    mid = (_uniform(0.25, 0.65, n_runs, gen, device) * hours).unsqueeze(1)
    # steeper growth when windier; normalized to the horizon scale
    steep = (hours / 10.0) / wind.unsqueeze(1)

    growth = torch.sigmoid((t.unsqueeze(0) - mid) / steep)  # [N,T]
    return torch.clamp(ceiling * growth, min=0.0, max=0.999)


_KERNELS = {
    "flood": _flood_kernel,
    "earthquake": _earthquake_kernel,
    "cyclone": _cyclone_kernel,
    "wildfire": _wildfire_kernel,
}


def _confidence_for(horizon: str) -> Confidence:
    # Uncertainty compounds with horizon length; labels, not numbers.
    return {"6h": "high", "24h": "medium", "72h": "low"}[horizon]


_DRIVERS = {
    "flood": [
        "rainfall intensity distribution (heavy-tailed)",
        "drainage capacity vs forcing",
        "population density band",
    ],
    "earthquake": [
        "building stock vulnerability",
        "aftershock sequence (Omori decay)",
        "population density band",
    ],
    "cyclone": [
        "track-cone uncertainty (hit vs near-miss)",
        "wind envelope timing and width",
        "rain/surge flood tail after landfall",
    ],
    "wildfire": [
        "wind factor (downslope events are the tail)",
        "containment ceiling",
        "fire-front growth timing",
    ],
}


def run_simulation(
    event: CrisisEvent,
    horizon: str = "24h",
    n_runs: int = DEFAULT_N_RUNS,
    force_cpu: bool = False,
    seed: int | None = None,
    n_chunks: int = 1,
    progress_cb=None,
) -> SimulationOutput:
    """Run the batched Monte Carlo for one event/horizon pair.

    `n_chunks` > 1 splits the batch into sequential sub-batches purely so
    real progress (runs completed so far) can stream to the UI via
    `progress_cb(runs_done, runs_total)` — each chunk is still one batched
    tensor op, never a per-run Python loop.
    """
    if event.kind not in _KERNELS:
        raise UnsupportedHazardError(
            f"no kernel for kind={event.kind!r}; supported: {SUPPORTED_KINDS}"
        )
    if horizon not in HORIZON_HOURS:
        raise ValueError(f"horizon must be one of {list(HORIZON_HOURS)}")
    if event.population_context is None:
        raise ValueError(f"event {event.id} has no population_context")

    device = get_device(force_cpu)
    hours = HORIZON_HOURS[horizon]
    pop = event.population_context
    density_mult = DENSITY_MULTIPLIER[pop.density_band]

    gen = torch.Generator(device=device)
    if seed is not None:
        gen.manual_seed(seed)

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
        logger.info(
            "sim start: device=%s vram_alloc=%.2fGB",
            _device_name(device),
            torch.cuda.memory_allocated(device) / 2**30,
        )

    n_chunks = max(1, min(n_chunks, n_runs))
    chunk_sizes = [n_runs // n_chunks] * n_chunks
    chunk_sizes[-1] += n_runs - sum(chunk_sizes)

    start = time.perf_counter()
    kernel = _KERNELS[event.kind]
    hazard_chunks: list[torch.Tensor] = []
    done = 0
    for size in chunk_sizes:
        hazard_chunks.append(kernel(event.severity, hours, size, gen, device))
        done += size
        if progress_cb is not None:
            progress_cb(done, n_runs)
    hazard = torch.cat(hazard_chunks, dim=0)  # [N,T]
    peak_frac = hazard.max(dim=1).values * density_mult  # [N]
    peak_frac = peak_frac.clamp(min=0.0, max=MAX_EXPOSURE_FRAC)
    exposed = torch.round(peak_frac * float(pop.exposed_estimate))  # [N]

    q = torch.quantile(exposed, torch.tensor([0.10, 0.90], device=device))
    severity_curve = hazard.mean(dim=0).clamp(0.0, 1.0)
    # Per-timestep p10/p90 envelope — the chart's honest uncertainty band.
    band = torch.quantile(
        hazard, torch.tensor([0.10, 0.90], device=device), dim=0
    ).clamp(0.0, 1.0)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    wall_ms = (time.perf_counter() - start) * 1000.0

    vram_gb = None
    if device.type == "cuda":
        vram_gb = torch.cuda.max_memory_allocated(device) / 2**30
        logger.info("sim end: peak_vram=%.2fGB wall=%.1fms", vram_gb, wall_ms)

    forecast = HorizonForecast(
        exposed_population=(int(q[0].item()), int(q[1].item())),
        severity_curve=[round(float(s), 4) for s in severity_curve.tolist()],
        severity_band_low=[round(float(s), 4) for s in band[0].tolist()],
        severity_band_high=[round(float(s), 4) for s in band[1].tolist()],
        confidence=_confidence_for(horizon),
        drivers=_DRIVERS[event.kind],
    )
    metrics = GpuMetrics(
        device=_device_name(device),
        n_runs=n_runs,
        batch_size=n_runs,  # one batch, by design (CLAUDE.md GPU rule)
        wall_ms=wall_ms,
        runs_per_sec=n_runs / (wall_ms / 1000.0) if wall_ms > 0 else 0.0,
        vram_gb=vram_gb,
    )
    return SimulationOutput(forecast=forecast, metrics=metrics, exposed=exposed)


def main() -> None:
    parser = argparse.ArgumentParser(description="CrisisCommand Monte Carlo engine")
    parser.add_argument("--event", default="seed-FL-001", help="seed event id")
    parser.add_argument("--horizon", default="24h", choices=list(HORIZON_HOURS))
    parser.add_argument("--runs", type=int, default=DEFAULT_N_RUNS)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--cpu", action="store_true",
        help="force CPU (produces the GPU-vs-CPU pitch comparison number)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from scripts.seed_events import load_seed_events

    events = {e.id: e for e in load_seed_events()}
    if args.event not in events:
        raise SystemExit(f"unknown event id {args.event!r}; try one of {list(events)}")
    event = events[args.event]

    out = run_simulation(
        event, horizon=args.horizon, n_runs=args.runs,
        force_cpu=args.cpu, seed=args.seed,
    )
    f, m = out.forecast, out.metrics
    print(json.dumps({
        "event": {"id": event.id, "kind": event.kind, "title": event.title},
        "horizon": args.horizon,
        "exposed_population_p10_p90": list(f.exposed_population),
        "confidence": f.confidence,
        "drivers": f.drivers,
        "severity_curve_head": f.severity_curve[:6],
        "gpu_metrics": m.model_dump(),
    }, indent=2))


if __name__ == "__main__":
    main()
