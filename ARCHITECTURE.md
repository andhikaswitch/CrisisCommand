# ARCHITECTURE.md — CrisisCommand System Design

## 1. System Context

```
┌──────────────────────────────────────────────────────────────────┐
│                         BROWSER (React)                          │
│     3D Globe (Three.js) + Holographic HUD panels + WS client     │
└───────────────┬──────────────────────────▲───────────────────────┘
                │ REST                     │ WebSocket
                ▼                          │
┌──────────────────────────────────────────┴───────────────────────┐
│                     FASTAPI BACKEND                              │
│  /api/events  /api/events/{id}/brief  /api/events/{id}/simulate  │
│  /api/events/{id}/options  /ws                                   │
└──┬───────────────┬────────────────┬────────────────┬─────────────┘
   │               │                │                │
   ▼               ▼                ▼                ▼
┌────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│INGEST  │  │ SIMULATION  │  │  BRIEFING    │  │ EMBEDDINGS   │
│Scheduler│ │  ENGINE     │  │  WRITER      │  │ (dedup/      │
│GDACS   │  │ MonteCarlo  │  │ Fireworks AI │  │  severity)   │
│USGS    │  │ (ROCm GPU)  │  │              │  │ ROCm GPU     │
│Relief  │  │     +       │  └──────────────┘  └──────────────┘
│Web     │  │ ScenarioAgent│
│News    │  │ (vLLM on    │
└────────┘  │  MI300X)    │
            └─────────────┘
```

Two AMD compute paths:
- **vLLM server** on the MI300X droplet serving an open LLM (OpenAI-compatible endpoint on localhost)
- **PyTorch/ROCm** in the backend process for Monte Carlo tensors + embeddings

## 2. Core Data Schema

```python
class CrisisEvent(BaseModel):
    id: str                       # source-prefixed, e.g. "gdacs-EQ-123"
    kind: Literal["earthquake","flood","cyclone","wildfire",
                  "volcano","drought","tension"]
    title: str
    lat: float
    lon: float
    country: str
    severity: float               # normalized 0-1 across sources
    started_at: datetime
    source: str                   # "GDACS" | "USGS" | "ReliefWeb" | "News"
    source_url: str
    raw: dict                     # original payload, never shown raw to user
    population_context: PopContext | None   # nearest-city population, density band

class SimulationResult(BaseModel):
    event_id: str
    horizons: dict[str, HorizonForecast]     # "6h" | "24h" | "72h"
    options: list[PolicyOption]              # exactly 3
    gpu_metrics: GpuMetrics                  # runs, batch size, wall_ms, device name
    generated_at: datetime

class HorizonForecast(BaseModel):
    exposed_population: tuple[int, int]      # p10, p90 range — never a point
    severity_curve: list[float]              # for the escalation chart
    confidence: Literal["low","medium","high"]
    drivers: list[str]                       # human-readable factors

class PolicyOption(BaseModel):
    id: str
    name: str                                # "Immediate staged evacuation"
    description: str
    exposed_population_after: tuple[int, int]
    est_cost_usd: tuple[int, int]
    response_time_hours: float
    tradeoffs: list[str]                     # honest cons
    affected_zones: list[GeoZone]            # polygons/radii for globe render
```

## 3. Ingestion Layer

| Source | What | Access | Poll |
|---|---|---|---|
| GDACS | Multi-hazard global alerts w/ severity | Public RSS/GeoJSON | 5 min |
| USGS | Earthquakes | Public GeoJSON feed | 5 min |
| ReliefWeb | Humanitarian situation reports | Public REST API | 15 min |
| News headlines | Geopolitical tension signals | NewsAPI or GDELT | 15 min |

Rules:
- Each ingestor is ~100 lines: fetch → map to `CrisisEvent` → emit. All quirks live in the ingestor, `normalizer.py` holds shared logic (severity normalization table, country geocoding).
- Dedup: new events embedded (GPU) and cosine-matched against active events; >0.92 similarity within 200km = same event, merge.
- **Seed mode (`SEED_MODE=true`)**: skips schedulers, loads `scripts/seed_events.py` (≈15 curated real historical events with full population context). This is the demo's safety net and the dev default.
- "tension" events come from clustered news headlines only, marked `confidence: low`, and are visually distinct on the globe (see UI_DESIGN.md). No prediction claims — signal detection only.

## 4. Simulation Engine (The AMD Core)

Two cooperating parts per simulation request:

### 4.1 Monte Carlo hazard engine — `monte_carlo.py` (PyTorch/ROCm)
- Input: event kind, severity, population context, horizon.
- Model: batched stochastic runs of hazard spread × exposure × response-delay. All parameters as tensors of shape `[N_RUNS]`, N_RUNS = 10,000 default.
- Per hazard kind, a parameterized kernel (flood: water-level growth curve + drainage factor; cyclone: track cone + wind decay; earthquake: aftershock exposure; wildfire: spread rate × wind). These are simplified, defensible models — documented assumptions in code comments, not black magic.
- Output: exposed-population distribution → p10/p90 bands + severity curve.
- Wall-time and device name recorded into `GpuMetrics`. A `--cpu` flag exists to produce the comparison number for the pitch ("4.2s on CPU → 0.3s on MI300X" or similar measured truth).

### 4.2 Scenario agent — `scenario_agent.py` (vLLM on MI300X)
- Takes the event + Monte Carlo stats, reasons over THREE policy branches in parallel (batched requests to local vLLM — this is where MI300X batching shines).
- Each branch call returns a structured `PolicyOption` JSON (prompt P2 in PROMPTS.md), grounded in the Monte Carlo numbers it is given — the LLM narrates and structures, the tensor engine quantifies. LLM never invents casualty numbers; it transforms given ranges.
- Validation + one repair retry; a failed branch degrades to a template option rather than failing the simulation.

### 4.3 Caching
`(event_id, horizon)` → result cached in-process + on disk. Re-click = instant. Cache invalidated if event severity updates >10%.

## 5. Briefing Writer (Fireworks)

- One call per event on first open: 150-word situation brief, structure per prompt P1.
- Quality-critical and low-volume → Fireworks API (managed, also AMD-powered infra — mention in pitch).
- Cached per event revision.

## 6. API Surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/events` | Active events (globe markers) |
| GET | `/api/events/{id}` | Full event detail |
| POST | `/api/events/{id}/brief` | Generate/fetch AI briefing |
| POST | `/api/events/{id}/simulate?horizon=24h` | Run/fetch simulation |
| GET | `/api/health/gpu` | Device name, VRAM, utilization (for HUD readout) |
| WS | `/ws` | `event_new`, `sim_progress`, `gpu_stats` messages |

### WS `sim_progress` example
```json
{"type":"sim_progress","event_id":"gdacs-FL-881","stage":"monte_carlo",
 "runs_done":6000,"runs_total":10000,"gpu_util_pct":91,"vram_gb":118.2}
```

## 7. Deployment

Same droplet pattern as documented in SETUP.md (AutoCine): MI300X droplet from vLLM Quick Start image.

```
On droplet:
  vllm serve <open-model> --port 8001          # scenario agent backend
  docker compose up                             # backend (8000) + frontend (3000)
Env: VLLM_ENDPOINT=http://localhost:8001/v1  SIM_BACKEND=vllm
Dev without droplet: SIM_BACKEND=fireworks SEED_MODE=true → everything runs locally.
```

Cost rules identical: stop droplet when idle; cache aggressively; 30-day credit clock.

## 8. Failure Modes

| Failure | Handling |
|---|---|
| Live API down/rate-limited | Ingestor logs + skips cycle; seed events remain; UI shows per-source freshness dot |
| vLLM endpoint unreachable | Auto-fallback to `SIM_BACKEND=fireworks`, HUD notes degraded mode |
| LLM invalid JSON | Repair retry → template option fallback |
| Globe <60fps | Progressive degradation ladder in UI_DESIGN.md §7 |
| Conference Wi-Fi dies | `SEED_MODE=true` full offline demo path — rehearsed, not theoretical |

## 9. Measured Numbers for the Pitch

- Monte Carlo: runs/sec on MI300X vs CPU (measured, not estimated)
- Scenario agent: 3 branches × N tokens batched on vLLM — tokens/sec
- Ingest-to-globe latency for a live GDACS event
- Peak VRAM with vLLM model + Monte Carlo + embeddings resident simultaneously (the 192GB story)
