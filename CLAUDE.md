# CLAUDE.md — CrisisCommand Project Instructions

## What This Project Is

CrisisCommand is an **AI war room for crisis decision-makers**, built for the AMD Developer Hackathon (Unicorn Track) by team Imitasi. It ingests real-time disaster and geopolitical data, runs AI-driven scenario simulations, and presents decision options on a **holographic 3D globe interface**.

The user (a crisis leader: government official, NGO coordinator, emergency manager) sees:
1. Live crisis events plotted on an interactive 3D Earth
2. For any selected crisis: an AI-simulated escalation forecast ("what happens in the next 6/24/72 hours if nothing is done")
3. Three concrete policy options, each with simulated impact (casualties averted, cost, response time)
4. A full AI-written situation briefing

**Positioning:** No open-source crisis simulation co-pilot exists. Commercial situational-awareness tools (Crisis24, Dataminr) show *what is happening* — CrisisCommand simulates *what to do about it*.

## Judging Criteria (Optimize for These)

1. **Creativity & originality** — decision simulation, not another news dashboard
2. **Completeness** — end-to-end: live data → simulation → recommendation → stunning UI
3. **Use of AMD platforms** — see "The AMD Story" below; this is engineered in, not bolted on
4. **Product/market potential** — governments, NGOs, insurers, logistics companies

## The AMD Story (This Must Be Real, Not Decorative)

The known weakness of this idea is "why does it need a GPU?" We answer it three ways — all three MUST exist in the demo:

1. **Self-hosted LLM on the AMD GPU via vLLM.** The scenario-simulation agents run on an open model (e.g., Llama/Qwen-class) served by vLLM ON the AMD GPU — not only via external API. Large HBM capacity lets us serve a model at high context length while BATCHING many simulation branches in parallel. Fireworks AI API is used for the lighter briefing/summarization calls. Both are AMD-powered (Fireworks runs on AMD infrastructure) — say this in the pitch.
2. **Parallel Monte Carlo scenario engine (PyTorch/ROCm).** Escalation forecasting runs thousands of stochastic simulations (population exposure × hazard spread × response delay) as batched tensor ops on the GPU. CPU fallback exists but is visibly slower — the demo shows the speedup number.
3. **GPU embedding pipeline.** News/report ingestion is embedded and clustered on-GPU for event deduplication and severity signals.

The UI displays a live GPU utilization readout during simulation. Visible AMD usage = judged AMD usage.

**Never hardcode a GPU model.** The Unicorn Track requires AMD hardware, not a
specific card. The ROCm notebook may allocate an Instinct part OR a Radeon/
Radeon PRO part (observed: gfx1100, 48GB, empty device name). Every readout, log line, and pitch number comes
from `backend/device.py::device_label()` — the app names the hardware it
actually ran on, falling back to the gfx arch when ROCm reports no name. Claiming an MI300X we did not use would be exactly the fake precision
this project forbids everywhere else.

## Repository Layout

```
crisiscommand/
├── CLAUDE.md                    # this file
├── ARCHITECTURE.md              # system design & data contracts
├── UI_DESIGN.md                 # holographic 3D globe UI specification
├── PROMPTS.md                   # all LLM prompts
├── IMPLEMENTATION_PLAN.md       # build schedule
├── docker-compose.yml
├── backend/
│   ├── main.py                  # FastAPI + WebSocket
│   ├── ingest/
│   │   ├── gdacs.py             # global disaster alerts (RSS/API)
│   │   ├── usgs.py              # earthquakes (GeoJSON feed)
│   │   ├── reliefweb.py         # humanitarian reports API
│   │   ├── news.py              # news headlines (tension signals)
│   │   └── normalizer.py        # all sources → CrisisEvent schema
│   ├── simulation/
│   │   ├── monte_carlo.py       # GPU tensor simulation engine (ROCm)
│   │   ├── scenario_agent.py    # LLM branch reasoning (vLLM local)
│   │   └── impact_model.py      # casualties/cost/time estimators
│   ├── briefing/
│   │   └── writer.py            # Fireworks AI situation briefings
│   ├── llm/
│   │   ├── vllm_client.py       # local AMD-GPU vLLM endpoint client
│   │   └── fireworks_client.py  # Fireworks API client
│   ├── models/                  # pydantic schemas
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── globe/               # Three.js / react-globe.gl scene
│   │   ├── panels/              # holographic HUD panels
│   │   └── lib/ws.js
│   └── package.json
└── scripts/
    ├── seed_events.py           # canned crisis dataset for offline demo
    └── smoke_test.py
```

## Core Engineering Rules

### Data & Honesty
- Every number shown to the user carries a confidence band and a source tag. This is a decision-support tool; fake precision is disqualifying.
- All simulations are labeled "SIMULATION" in the UI. Impact estimates show ranges (e.g., "800–2,400 people exposed"), never single hard numbers.
- The demo MUST work offline: `seed_events.py` loads a curated set of real historical events (2004 tsunami region profile, Jakarta flood profile, etc.) so a dead conference Wi-Fi cannot kill the demo. Live APIs are a layer on top.

### GPU / ROCm
- Device string is `"cuda"` (ROCm presents as cuda). Code stays device-agnostic; local dev on NVIDIA is fine.
- `monte_carlo.py` is pure batched tensor math — no Python loops over simulation runs. Target: 10,000 scenario runs as one batch.
- vLLM serves the simulation model on whichever AMD GPU environment is available (droplet or ROCm notebook); `vllm_client.py` speaks OpenAI-compatible protocol to it. If no GPU endpoint is up during dev, a config flag routes scenario calls to Fireworks instead (`SIM_BACKEND=vllm|fireworks`).
- Log GPU memory + utilization at simulation start/end; stream to the UI readout.

### LLM Usage Split
| Task | Backend | Why |
|---|---|---|
| Scenario branch reasoning (many parallel calls) | vLLM on the AMD GPU | Batching, cost-free once running, THE AMD story |
| Situation briefing (few, quality-critical) | Fireworks API | Managed reliability, also AMD-powered |
| Event summarization on ingest | vLLM local | High volume |

### Pipeline Behavior
- Ingestors run on a scheduler (every 5 min live mode; instant in seed mode) and normalize into `CrisisEvent`.
- Simulation is on-demand per event (user clicks a crisis) — not continuous. Results cached per (event, horizon) pair.
- WebSocket streams: new events, simulation progress, GPU stats.
- LLM JSON outputs validated against pydantic schemas; one repair-prompt retry (same pattern as PROMPTS.md P-R).

### Frontend
- Three states around one persistent globe: `overview → crisis selected → simulation running/results`.
- Globe is the centerpiece; panels float around it. Full spec in UI_DESIGN.md — read it before touching frontend code.
- No localStorage/sessionStorage; state in React memory.
- Must hold 60fps on the globe with ≤200 event markers; degrade gracefully (disable atmosphere shader first) below that.

### Testing
- `smoke_test.py`: seed events → run one simulation (small batch) → assert recommendation JSON valid.
- Unit tests: normalizers per source, Monte Carlo tensor shapes, schema validation, impact model bounds.
- GPU tests marked `@pytest.mark.gpu`.

## What NOT to Build (Scope Guard)

- ❌ Real alerting/notification to authorities (demo tool, not production emergency system)
- ❌ Social media ingestion (rabbit hole; news headlines suffice for tension signals)
- ❌ User accounts, multi-tenancy, saved sessions
- ❌ Mobile layout (desktop demo only)
- ❌ Prediction of earthquakes (impossible; we simulate RESPONSE to events, and forecast weather-driven hazards only from official feeds)

## Ethical Guardrails

- Recommendations are always framed as options for a human decision-maker with explicit trade-offs — never "the AI decided."
- No simulation of offensive military actions. Scope = disaster response + humanitarian logistics + tension monitoring.
- Historical seed data uses public, documented events.

## Demo Script (What Judges See)

1. Globe spins into view — live events glowing on Earth. ("Every marker is a real event from GDACS/USGS, ingested minutes ago.")
2. Click the flood event in Jakarta. Camera flies down; holographic panel opens with the AI briefing.
3. Hit SIMULATE — GPU readout spikes (naming the actual card), 10,000 Monte Carlo runs + LLM branch reasoning on the AMD GPU, escalation curve draws itself for 6/24/72h horizons.
4. Three policy cards appear: evacuate zones A–C now / pre-position supplies / monitor. Each shows exposed-population range, cost, response time.
5. Click one → globe renders the affected zones and evacuation radius in 3D. ("Commercial tools show you the crisis. This simulates your decision.")

## Environment

- AMD Developer Cloud: GPU droplet (vLLM Quick Start image) **or** the ROCm Jupyter notebook (ROCm 7.2 + vLLM 0.16 + PyTorch 2.9 preinstalled). Either satisfies the track; the card model is whatever the environment allocates.
- Python 3.11, Node 20; Fireworks API key
- Env vars: `FIREWORKS_API_KEY`, `FIREWORKS_MODEL`, `VLLM_ENDPOINT`, `SIM_BACKEND`, `SEED_MODE`
- See AutoCine SETUP.md equivalent steps for credits/droplet (same accounts, same rules: stop droplet when idle, 30-day credit clock)

## Development Workflow for Claude

1. Read ARCHITECTURE.md contracts before implementing a component; read UI_DESIGN.md before any frontend work.
2. Build order per IMPLEMENTATION_PLAN.md. Seed/offline mode comes BEFORE live APIs.
3. Backend stage → unit test → wire → frontend, in that order.
4. Flag ROCm-specific concerns with `# ROCM:` comments.
