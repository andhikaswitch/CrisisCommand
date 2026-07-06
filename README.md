# 🌍 CrisisCommand

**Dashboards show you the crisis. CrisisCommand simulates your decision.**

An AI war room for crisis leaders, built for the AMD Developer Hackathon: ACT II (Unicorn Track) by team **Imitasi**. Live disaster and tension data flows onto a holographic 3D Earth; for any crisis, an AI simulation engine forecasts escalation and presents three grounded response options — with honest numbers, ranges, and trade-offs.

## The Gap

Commercial situational-awareness tools (Crisis24, Dataminr) and public dashboards (GDACS, ReliefWeb) tell decision-makers *what is happening*. None of them simulate *what happens next under each possible response*. That decision layer — the hard part — is what CrisisCommand builds, and no open-source equivalent exists.

## Why AMD (Engineered In, Not Bolted On)

- **Self-hosted LLM on MI300X via vLLM** — scenario-branch reasoning runs batched on the AMD GPU; 192GB HBM3 keeps the LLM, Monte Carlo engine, and embedding pipeline resident simultaneously
- **GPU Monte Carlo engine (PyTorch/ROCm)** — 10,000 stochastic hazard-exposure simulations as one tensor batch; measured CPU-vs-MI300X speedup shown live in the UI
- **Fireworks AI** (itself AMD-powered) handles quality-critical situation briefings
- A live MI300X utilization readout sits in the interface — AMD usage you can *see* during the demo

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

## Quick Start (once built)

```bash
cp .env.example .env               # FIREWORKS_API_KEY, SIM_BACKEND, SEED_MODE
docker compose up --build          # backend :8000, frontend :3000
# SEED_MODE=true → full offline demo with curated real historical events
# On the MI300X droplet: vllm serve <model> --port 8001 first
python scripts/smoke_test.py
```

## Demo Flow (60 seconds of judge attention)

1. Globe spins into view, live GDACS/USGS events pulsing
2. Click the Jakarta flood → camera flies, AI briefing streams in
3. RUN SIMULATION → MI300X readout spikes, 10,000 Monte Carlo runs, escalation curve draws
4. Three response options appear with population-exposure ranges before → after
5. Select one → evacuation zones and supply arcs render on the Earth in 3D

## Team

**Imitasi** — Built with AMD Instinct MI300X · ROCm · vLLM · Fireworks AI · PyTorch · FastAPI · React · Three.js
