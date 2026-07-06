"""CrisisCommand FastAPI backend.

Serves seed events (SEED_MODE=true is the dev default per ARCHITECTURE.md §3),
the GPU health readout, AI situation briefings (P1), and the full simulate
endpoint (Monte Carlo + grounded policy options). The WebSocket lands Day 4.

Run:  uvicorn backend.main:app --reload --port 8000
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import torch  # noqa: E402
from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.briefing.writer import write_briefing  # noqa: E402
from backend.models import (  # noqa: E402
    HORIZON_HOURS,
    Briefing,
    CrisisEvent,
    Horizon,
    SimulationResult,
)
from backend.simulation.monte_carlo import (  # noqa: E402
    DEFAULT_N_RUNS,
    UnsupportedHazardError,
)
from backend.simulation.orchestrator import run_full_simulation  # noqa: E402

SEED_MODE = os.getenv("SEED_MODE", "true").lower() in ("1", "true", "yes")

app = FastAPI(title="CrisisCommand", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo tool; single-operator, no auth by design
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_events() -> list[CrisisEvent]:
    if SEED_MODE:
        from scripts.seed_events import load_seed_events

        return load_seed_events()
    # Live ingestion lands Day 5; until then non-seed mode serves nothing.
    return []


def _require_event(event_id: str) -> CrisisEvent:
    for e in _load_events():
        if e.id == event_id:
            return e
    raise HTTPException(status_code=404, detail=f"unknown event {event_id!r}")


@app.get("/api/events", response_model=list[CrisisEvent])
def list_events() -> list[CrisisEvent]:
    return _load_events()


@app.get("/api/events/{event_id}", response_model=CrisisEvent)
def get_event(event_id: str) -> CrisisEvent:
    return _require_event(event_id)


@app.post("/api/events/{event_id}/brief", response_model=Briefing)
async def brief_event(event_id: str) -> Briefing:
    """P1 situation briefing (Fireworks; raw-data fallback offline)."""
    event = _require_event(event_id)
    return await write_briefing(event)


@app.post("/api/events/{event_id}/simulate", response_model=SimulationResult)
async def simulate_event(
    event_id: str,
    horizon: Horizon = Query("24h"),
    runs: int = Query(DEFAULT_N_RUNS, ge=100, le=200_000),
) -> SimulationResult:
    """Full simulation: Monte Carlo (6h/24h/72h) + three grounded options."""
    event = _require_event(event_id)
    if horizon not in HORIZON_HOURS:
        raise HTTPException(status_code=422, detail=f"bad horizon {horizon!r}")
    try:
        return await run_full_simulation(event, horizon=horizon, n_runs=runs)
    except UnsupportedHazardError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/health/gpu")
def gpu_health() -> dict:
    # ROCM: ROCm presents as cuda; on the MI300X droplet this reports the
    # Instinct device name and real VRAM numbers for the HUD readout.
    if torch.cuda.is_available():
        idx = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(idx)
        return {
            "device": torch.cuda.get_device_name(idx),
            "backend": "gpu",
            "vram_total_gb": round(props.total_memory / 2**30, 1),
            "vram_used_gb": round(torch.cuda.memory_allocated(idx) / 2**30, 2),
        }
    return {"device": "cpu", "backend": "cpu", "vram_total_gb": None,
            "vram_used_gb": None}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "seed_mode": SEED_MODE}
