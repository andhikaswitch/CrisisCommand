# 🌍 CrisisCommand

**Dashboards show you the crisis. CrisisCommand simulates your decision.**

An AI war room for crisis leaders, built for the AMD Developer Hackathon: ACT II (Unicorn Track) by team **Imitasi**. Live disaster and tension data flows onto a holographic 3D Earth; for any crisis, an AI simulation engine forecasts escalation and presents three grounded response options — with honest numbers, ranges, and trade-offs.

## The Gap

Commercial situational-awareness tools (Crisis24, Dataminr) and public dashboards (GDACS, ReliefWeb) tell decision-makers *what is happening*. None of them simulate *what happens next under each possible response*. That decision layer — the hard part — is what CrisisCommand builds, and no open-source equivalent exists.

## Why AMD (Engineered In, Not Bolted On)

- **Self-hosted LLM on AMD Instinct via vLLM** — scenario-branch reasoning runs batched on the AMD GPU; large HBM keeps the LLM, Monte Carlo engine, and embedding pipeline resident simultaneously
- **GPU Monte Carlo engine (PyTorch/ROCm)** — 10,000 stochastic hazard-exposure simulations as one tensor batch; measured CPU-vs-GPU speedup shown live in the UI
- **Fireworks AI** (itself AMD-powered) handles quality-critical situation briefings
- A live GPU utilization readout sits in the interface — AMD usage you can *see* during the demo

Device-agnostic by construction: ROCm presents as `cuda`, and every readout
names whatever card the backend self-reports (MI300X, MI250, MI210, …). No GPU
model is hardcoded anywhere, so the demo always tells the truth about the
hardware it actually ran on.

## The Interface

One persistent 3D Earth in dark space — cyan atmosphere, pulsing severity rings, tension diamonds — surrounded by translucent holographic HUD panels with cut corners and scanlines. Click a crisis: the camera flies in, an AI briefing streams in, and one button runs the simulation while the GPU readout spikes. Full spec: [UI_DESIGN.md](UI_DESIGN.md).

## Honest by Design

- Every figure is a **range** (p10–p90), never false precision
- The LLM **never invents numbers** — it structures options around Monte Carlo outputs and vetted mitigation factors only
- Everything simulated is labeled `SIMULATION — DECISION SUPPORT ONLY`
- A human decision-maker chooses; the AI presents trade-offs

## Documentation Map

| File | Contents | Read when |
|---|---|---|
| [CLAUDE.md](CLAUDE.md) | Project rules, AMD story, repo layout, scope guard, demo script | Starting any session |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Data schema, ingestion, simulation engine, API, deployment | Implementing components |
| [UI_DESIGN.md](UI_DESIGN.md) | Complete holographic globe interface spec (closed spec) | Any frontend work |
| [PROMPTS.md](PROMPTS.md) | All LLM prompts + grounding rules | Touching LLM behavior |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Day 0–7 schedule, risks, labor split | Daily planning |
| [DEPLOY.md](DEPLOY.md) | AMD GPU runbook (droplet or ROCm notebook) + evidence capture | Deploying / capturing pitch metrics |

## Quick Start

### Docker (one command, works offline)

```bash
cp .env.example .env               # SEED_MODE=true by default — no keys needed
docker compose up --build          # frontend → http://localhost:3000
```

The full demo runs offline against 15 curated historical events. nginx proxies
`/api` and `/ws` to the backend, so the browser uses a single origin.

### Local dev (no Docker)

```bash
python -m venv .venv && .venv/bin/pip install torch fastapi "uvicorn[standard]" pydantic httpx pytest
.venv/bin/uvicorn backend.main:app --port 8000            # backend
cd frontend && npm install && npm run dev                 # frontend → :3000
```

Ports 8000/3000 taken? Override: `uvicorn … --port 8055` and
`PORT=5173 BACKEND_URL=http://localhost:8055 npm run dev`.

### Verify

```bash
python -m pytest                   # 111 tests
python scripts/smoke_test.py       # end-to-end: seed → Monte Carlo → 3 options
python scripts/failure_drills.py   # 5 induced-failure drills
```

### AMD GPU (droplet or ROCm notebook) + live mode

Real GDACS/USGS ingestion and self-hosted vLLM: see **[DEPLOY.md](DEPLOY.md)**.
Short version — `SEED_MODE=false` for live feeds, `SIM_BACKEND=vllm` with
`vllm serve <model> --port 8001` for the on-GPU scenario agent.

## Demo Flow (60 seconds of judge attention)

1. Globe spins into view, live GDACS/USGS events pulsing
2. Click the Jakarta flood → camera flies, AI briefing streams in
3. RUN SIMULATION → GPU readout spikes, 10,000 Monte Carlo runs, escalation curve draws
4. Three response options appear with population-exposure ranges before → after
5. Select one → evacuation zones and supply arcs render on the Earth in 3D

## Pitch

Self-contained 8-slide deck: open [pitch/index.html](pitch/index.html) in any
browser (offline, no build). The gap → live demo → the AMD story → honest-by-design
→ market → roadmap.

## Build Status

| Layer | State |
|---|---|
| Schemas, seed dataset, Monte Carlo engine (flood, quake, cyclone, wildfire kernels) | ✅ |
| LLM layer: grounded 3-option generation, briefings, template fallback | ✅ |
| Holographic globe UI: Modes A→B→C, escalation chart, option zones | ✅ |
| WebSocket sim progress + live GPU readout (self-reported device) | ✅ |
| Live ingestion: USGS, GDACS, BMKG, rain-driven flood risk, GDELT tension | ✅ |
| Hardening: quality ladder, 5 failure drills, honest fallback banner | ✅ |
| AMD GPU deploy + evidence capture | ▶ [DEPLOY.md](DEPLOY.md) |

## Team

**Imitasi** — Built with AMD Instinct GPUs · ROCm · vLLM · Fireworks AI · PyTorch · FastAPI · React · Three.js
