"""CrisisCommand FastAPI backend.

Serves seed events (SEED_MODE=true is the dev default per ARCHITECTURE.md §3),
the GPU health readout, AI situation briefings (P1), and the full simulate
endpoint (Monte Carlo + grounded policy options). The WebSocket lands Day 4.

Run:  uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.env import load_dotenv  # noqa: E402

# Before any module reads os.getenv: a bare `uvicorn backend.main:app` must see
# FIREWORKS_API_KEY, or briefings silently degrade to the template fallback.
load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import (  # noqa: E402
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.briefing.writer import write_briefing  # noqa: E402
from backend.ingest.store import EventStore  # noqa: E402
from backend.llm.client import (  # noqa: E402
    get_briefing_client,
    get_scenario_client,
    vllm_reachable,
)
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
from backend.ws import gpu_snapshot, manager  # noqa: E402

SEED_MODE = os.getenv("SEED_MODE", "true").lower() in ("1", "true", "yes")

# The active-event store: seeded in both modes (seed events are the safety
# net). In LIVE mode the scheduler adds real GDACS/USGS events on top.
store = EventStore(seed=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if not SEED_MODE:
        from backend.ingest.scheduler import scheduler_loop

        task = asyncio.create_task(scheduler_loop(store, broadcast=manager.broadcast))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()


app = FastAPI(title="CrisisCommand", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo tool; single-operator, no auth by design
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_event(event_id: str) -> CrisisEvent:
    event = store.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"unknown event {event_id!r}")
    return event


@app.get("/api/events", response_model=list[CrisisEvent])
def list_events() -> list[CrisisEvent]:
    return store.snapshot()


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
    """Full simulation: Monte Carlo (6h/24h/72h) + three grounded options.

    Progress streams to all WS clients as `sim_progress` messages while
    this request runs (the HUD's AMD-GPU moment).
    """
    event = _require_event(event_id)
    if horizon not in HORIZON_HOURS:
        raise HTTPException(status_code=422, detail=f"bad horizon {horizon!r}")

    def _progress(stage: str, done: int, total: int) -> None:
        snap = gpu_snapshot()
        manager.broadcast_threadsafe({
            "type": "sim_progress",
            "event_id": event.id,
            "horizon": horizon,
            "stage": stage,
            "runs_done": done,
            "runs_total": total,
            "vram_gb": snap["vram_used_gb"],
        })

    try:
        return await run_full_simulation(
            event, horizon=horizon, n_runs=runs, progress_cb=_progress
        )
    except UnsupportedHazardError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        # e.g. a live event with no curated population_context — we refuse to
        # invent an exposure base (honesty rule), so it is not simulable.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Streams event_new / sim_progress / gpu_stats to the HUD."""
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive pings; content ignored
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.get("/api/health/gpu")
def gpu_health() -> dict:
    return gpu_snapshot()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "seed_mode": SEED_MODE}


@app.get("/api/status")
async def status() -> dict:
    """Mode, per-source freshness, and LLM backend state for the HUD.

    `sim_backend_degraded` is true when vLLM was requested but is not
    reachable, so the frontend can show the honest fallback banner (§8).
    """
    now = datetime.now(timezone.utc)
    requested = os.getenv("SIM_BACKEND", "fireworks").lower()
    if requested == "vllm":
        reachable = await vllm_reachable()
        degraded = not reachable
        active = "vllm" if reachable else (
            "fireworks" if get_briefing_client().config.configured else "template"
        )
    else:
        degraded = False
        active = "fireworks" if get_briefing_client().config.configured else "template"
    return {
        "mode": "SEED" if SEED_MODE else "LIVE",
        "sim_backend_requested": requested,
        "sim_backend_active": active,
        "sim_backend_degraded": degraded,
        "briefing_backend_configured": get_briefing_client().config.configured,
        "sources": [
            {
                "source": h.source,
                "status": h.status(now),
                "event_count": h.event_count,
                "last_success": h.last_success.isoformat() if h.last_success else None,
                "last_error": h.last_error,
            }
            for h in store.source_health()
        ],
    }


# --- Single-origin SPA hosting (remote notebook / one-tunnel demos) --------
# In Docker, nginx serves the built SPA and proxies /api + /ws. On a cloud
# notebook there is no nginx and only one port can practically be tunnelled,
# so serve frontend/dist from this app when it exists. The frontend calls
# same-origin /api and /ws (lib/ws.js uses window.location.host), which keeps
# the WebSocket working through a single tunnel with no CORS.
# Mounted last so it never shadows the API routes above.
_DIST = _ROOT / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles  # noqa: E402

    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
