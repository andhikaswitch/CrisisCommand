# IMPLEMENTATION_PLAN.md — CrisisCommand 7-Day Build

## Ground Rules

- Same discipline as before: a stage is done when `smoke_test.py` passes through it. Daily end-to-end demo, however ugly.
- **Seed mode first, live APIs second.** The demo must never depend on external APIs being up.
- Local dev on NVIDIA/CPU with `SIM_BACKEND=fireworks SEED_MODE=true`; the MI300X droplet is used at defined checkpoints (Days 2, 6) and stopped afterwards ($1.99/hr).

---

## Day 0 — Access & Credits (before the clock starts)

Identical checklist to SETUP.md: Fireworks account + $6 starter, hackathon $50 chased on Discord, AMD Cloud credit form submitted (2–3 day approval — submit NOW), droplet NOT activated until needed.

## Day 1 — Schemas, Seed Data, Monte Carlo Core

**Goal: the quantitative heart works, offline.**

- [x] Repo scaffold per CLAUDE.md; pydantic schemas (`CrisisEvent`, `SimulationResult`, `PolicyOption`, …) (2026-07-07)
- [x] `seed_events.py`: 15 curated real historical events across kinds (flood Jakarta, 3 quakes, 2 cyclones, 2 wildfires, volcano, drought, 2 tension signals) with population context (2026-07-07)
- [x] `monte_carlo.py`: flood + earthquake kernels as batched tensors; p10/p90 extraction; severity curves; unit tests on shapes and bounds; `--cpu` flag (2026-07-07)
- [x] FastAPI skeleton: `/api/events` serving seed data (2026-07-07)

**Exit:** 10,000-run flood simulation returns sane ranges on local hardware in one command.

## Day 2 — LLM Layer + First AMD Checkpoint

- [x] `fireworks_client.py` + `vllm_client.py` (one OpenAI-compatible wrapper in `llm/client.py`, two configs, auto-fallback) (2026-07-07)
- [x] P1 briefing — validated, P-R repair retry, raw-data fallback, cached per revision (2026-07-07)
- [x] P2 three-branch option generation grounded in Monte Carlo output; P-R repair path; template-option fallback; numbers recomputed server-side (no invented numbers) (2026-07-07)
- [x] Caching layer for P1/P2 (in-process + disk) (2026-07-07)
- [ ] **MI300X checkpoint (droplet on → work → droplet OFF):** — BLOCKED on droplet access; code is ready (`SIM_BACKEND=vllm`), run when the droplet is up
  - `vllm serve` an open instruct model; P2 batch of 3 branches through it
  - `monte_carlo.py` on ROCm: record runs/sec vs CPU number (pitch evidence)
  - remaining hazard kernels (cyclone, wildfire) if time allows

**Exit:** full simulate endpoint (`POST /simulate`) returns a complete `SimulationResult` from seed data. ✅ verified offline (template path); live vLLM/Fireworks path uses the same wrapper and runs when a key/droplet is present.

## Day 3 — Globe Foundation

- [x] React app (Vite) + full-viewport `react-globe.gl` scene: dark earth, cyan atmosphere, CSS starfield, auto-rotate 0.3°/s w/ drag-pause (2026-07-07)
- [x] Globe look decided: HEX POLYGONS (bundled Natural Earth GeoJSON — offline-safe, more holographic; texture variant rejected: needs runtime download) (2026-07-07)
- [x] Event markers from `/api/events`: severity-colored pulsing rings + center dots, violet tension diamonds (no alarm pulse) (2026-07-07)
- [x] Click → 1.2s camera flight → selection state; rails slide out during flight and return (2026-07-07)
- [x] `<HoloPanel>` component per UI_DESIGN.md §3 spec (cut corners, brackets, scanline, top sweep, glitch mount) (2026-07-07)
- [x] Top bar (UTC clock, SEED/LIVE badge) + left event feed rail + right context panel w/ radar-sweep empty state (2026-07-07)

**Exit:** globe with live seed markers, click-to-fly working, one holo panel rendering. ✅ verified via headless-browser screenshots (Mode A + Mode B), zero console errors.

## Day 4 — The Full Flow (Modes A→B→C)

- [ ] Right rail: briefing panel with typewriter stream
- [ ] RUN SIMULATION → WS `sim_progress` wiring → progress panel with live run counts
- [ ] Bottom GPU readout bar consuming `/api/health/gpu` + WS `gpu_stats`
- [ ] Results: escalation chart (p10–p90 band, horizon tabs) + three `PolicyOptionCard`s
- [ ] Option hover/select → zones + supply arcs on globe, cross-fade between options
- [ ] "SIMULATION — DECISION SUPPORT ONLY" labeling throughout

**Exit:** the complete demo flow works end-to-end in seed mode on a laptop.

## Day 5 — Live Ingestion + Hardening

- [ ] GDACS + USGS ingestors (the two easiest, most reliable feeds) → normalizer → dedup via GPU/CPU embeddings
- [ ] ReliefWeb + news/tension ingestors if the first two land by lunch; otherwise cut — seed tension events suffice
- [ ] Freshness dots, LIVE/SEED indicator, vLLM-fallback banner
- [ ] Deliberate failure drills: kill feeds, kill vLLM, invalid LLM JSON, mid-sim disconnect/reconnect
- [ ] Performance pass on globe (200-marker synthetic load, quality-ladder wiring)

**Exit:** app runs in LIVE mode with real GDACS/USGS events appearing; survives every induced failure; still demos perfectly in SEED mode.

## Day 6 — MI300X Full Deployment + Evidence Capture

- [ ] Droplet up: vLLM serving + backend + frontend via docker compose per ARCHITECTURE.md §7
- [ ] Full demo flow ×3 consecutive runs on the droplet without intervention
- [ ] Capture pitch evidence: Monte Carlo GPU-vs-CPU numbers, vLLM tokens/sec on batched branches, peak VRAM with everything resident, screen recordings of the GPU readout spiking
- [ ] Record the backup demo video (non-negotiable)
- [ ] **Droplet OFF at end of day**
- [ ] No new features today

**Exit:** three clean runs recorded; metrics table filled; backup video exists.

## Day 7 — Pitch + Submission

- [ ] Deck (≤8 slides): the gap (dashboards show, nobody simulates) → live demo → the AMD story (vLLM + Monte Carlo numbers, 192GB all-resident) → ethics slide (ranges, human-in-the-loop, no invented numbers) → market (governments, NGOs, insurers, logistics) → roadmap
- [ ] README any judge can follow; docker compose verified from clean clone
- [ ] Dry-run the live demo twice; seed mode as stage default, live mode as flourish if Wi-Fi cooperates
- [ ] Submit early

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Globe performance tanks with effects | Med | Quality ladder (UI_DESIGN §7); hex-vs-texture decision Day 3 |
| vLLM model won't serve on droplet image | Low-Med | vLLM Quick Start image is purpose-built for this; fallback `SIM_BACKEND=fireworks` always works |
| Live feeds flaky during judging | High | SEED mode is the rehearsed default; live is bonus |
| P2 numbers drift from Monte Carlo grounding | Med | Validator recomputes arithmetic; template fallback |
| Credits delayed | Med | Whole build runs local until Day 2 checkpoint; Day 2 GPU work can slip to Day 6 worst case |
| Scope creep into more panels/effects | High | UI_DESIGN.md is a closed spec — nothing not in it gets built |

## Division of Labor (2–3 people)

- **A (backend/ML):** Days 1–2 schemas + Monte Carlo + LLM layer; Day 5 ingestors; Day 6 droplet
- **B (frontend):** Days 3–4 globe + HUD (owns UI_DESIGN.md); Day 5 performance
- **C/shared:** seed dataset curation, prompts tuning, failure drills, deck, evidence capture

Solo? Order stands; cut: ReliefWeb/news ingestors (seed tension only), sound, hex-polygon variant, cyclone/wildfire kernels (ship flood + quake).
