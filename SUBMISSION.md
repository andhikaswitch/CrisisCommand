# SUBMISSION.md — copy-paste answers for the hackathon form

Every claim below is verifiable in this repo. Do not add numbers that are not.
Update this file whenever the build status changes.

---

## Submission Title (5–50 chars)

```
CrisisCommand
```

Alternative if a longer title is preferred (49 chars):

```
CrisisCommand — AI War Room for Crisis Decisions
```

---

## Short Description (50–255 chars)

```
Dashboards show you the crisis. CrisisCommand simulates your decision: live disaster feeds land on a holographic 3D globe, then a GPU Monte Carlo engine and open LLMs forecast escalation and present three response options with honest ranges.
```

(238 characters.)

---

## Long Description (600–2000 chars, 100+ words)

```
Commercial situational-awareness tools (Crisis24, Dataminr) and public dashboards (GDACS, ReliefWeb) tell a crisis leader WHAT is happening. None simulate what happens next under each response. That decision layer is the hard part, and no open-source equivalent exists. CrisisCommand builds it.

Four live feeds stream onto a holographic 3D Earth: USGS earthquakes, GDACS multi-hazard alerts, Indonesia's BMKG seismic network, and rain-driven flood-risk signals computed from official forecasts crossed with documented flood history. GDELT headline density adds low-confidence tension signals. Clicking a crisis opens an AI situation briefing; pressing SIMULATE runs 10,000 stochastic hazard-exposure scenarios as one batched tensor operation, then an LLM reasons over three policy branches: evacuate now, pre-position and act on triggers, or monitor. Each option carries an exposed-population range, cost band, response time, and trade-offs. Selecting one renders the affected zones in 3D.

The AMD story is engineered in, not bolted on. The Monte Carlo engine is pure batched PyTorch/ROCm tensor math, no Python loops over runs. The code path is device-agnostic: ROCm presents as cuda, and the UI names whichever card the backend self-reports. We never hardcode a GPU model. vLLM serves the scenario-reasoning model on the AMD GPU, where batching parallel branches pays off, while Fireworks AI (itself AMD-powered) handles briefings. Deduplication embeds and clusters on-GPU.

Honesty is a hard rule, not a feature. Every figure is a p10–p90 range, never false precision. The LLM only does arithmetic on Monte Carlo outputs; it never invents numbers. Live events lacking vetted population data are deliberately NOT simulable: inventing an exposure base is worse than showing nothing. Everything is labelled SIMULATION, DECISION SUPPORT ONLY, and a human always chooses: these are options with trade-offs, never "the AI decided." The demo runs offline against 15 curated historical events.
```

---

## Categories

Pick what the form offers, in priority order:

- Disaster / Emergency Response (or Social Good / Public Sector)
- Data Visualization
- Generative AI / LLM
- Simulation

---

## Event Track

```
Unicorn Track
```

---

## Technologies used

Select from the list: **AMD Developer Cloud**, **Fireworks AI**, plus (typed if free-text):
ROCm · PyTorch · vLLM · FastAPI · React · Three.js / react-globe.gl · Python · WebSocket

---

## What it does / How we built it (if asked separately)

Backend: FastAPI + WebSocket. `monte_carlo.py` holds four hazard kernels
(flood, earthquake, cyclone track-cone, wildfire spread×wind), each a
documented, defensible stochastic model reduced to a p10/p90 exposed-population
band and a mean escalation curve. `orchestrator.py` chains Monte Carlo → LLM
policy options → validated JSON. Ingestors normalise every source into one
`CrisisEvent` schema. Frontend: React + react-globe.gl, one persistent globe
with three interaction states.

---

## Verifiable build facts (do not overstate these)

| Claim | How a judge can check |
|---|---|
| 146 automated tests pass | `python -m pytest` |
| End-to-end path works | `python scripts/smoke_test.py` |
| Degrades honestly under failure | `python scripts/failure_drills.py` (5 induced failures) |
| Runs fully offline | `docker compose up --build` with `SEED_MODE=true` |
| CPU-vs-GPU speedup: **61.2× at 100k runs** (30.4M runs/sec, AMD gfx1100, ROCm 7.2) | `evidence/benchmark.json` — measured, not estimated |
| No hardcoded GPU model | `grep -r MI300X backend/ frontend/src` |

---

## Demo video script (60 seconds)

1. Globe spins into view, live events pulsing. "Every marker is a real event
   from USGS, GDACS or BMKG, ingested minutes ago."
2. Click the Jakarta flood. Camera flies in, AI briefing streams in.
3. Press SIMULATE. GPU readout spikes and names the card. 10,000 Monte Carlo
   runs; the escalation curve draws itself across 6/24/72h.
4. Three policy cards appear with exposed-population ranges before → after.
5. Select one. Evacuation zones render on the Earth in 3D.
   "Commercial tools show you the crisis. This simulates your decision."

---

## Pre-submission checklist

- [ ] `python -m pytest` green
- [ ] `python scripts/smoke_test.py` passes
- [ ] `evidence/benchmark.json` captured on an AMD GPU (see DEPLOY.md §0.6)
- [ ] Demo video recorded (offline seed mode — never trust venue Wi-Fi)
- [ ] Repo public; `.env` NOT committed (it is gitignored — verify with
      `git log -p | grep -i fireworks_api_key` returning nothing)
- [ ] README screenshot / pitch deck (`pitch/index.html`) opens offline
