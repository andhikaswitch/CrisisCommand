# DEPLOY.md — CrisisCommand on the AMD MI300X Droplet

Turnkey runbook for Day 6 (MI300X full deployment + evidence capture). Two
tiers: the **default seed demo** runs anywhere with Docker; the **MI300X GPU
path** adds the real vLLM + ROCm compute that is the AMD story.

Cost discipline (same as every AMD droplet): **stop the droplet when idle**,
cache aggressively, the 30-day credit clock is real. Nothing below leaves a
GPU running longer than the capture needs.

---

## 0. Prerequisites

- AMD Developer Cloud MI300X droplet from the **vLLM Quick Start image**
  (vLLM + ROCm PyTorch preinstalled — exactly what we need).
- Repo cloned on the droplet; Docker + Docker Compose available.
- Optional: `FIREWORKS_API_KEY` for the P1 briefings (falls back to a
  raw-data brief without it — the demo still runs).

---

## 1. Seed demo (works anywhere, no GPU)

The rehearsed default. Verifiable from a clean clone on any machine.

```bash
cp .env.example .env          # SEED_MODE=true, SIM_BACKEND=fireworks
docker compose up --build     # backend :8000, frontend :3000
# open http://localhost:3000
```

Everything (globe, briefing, simulation, options) runs offline against the
15 curated historical events. Monte Carlo runs on CPU in-container.

---

## 2. MI300X GPU path (the AMD showcase)

On the droplet, run the LLM server and the Monte Carlo/embedding backend on
the **host** (so they see the ROCm GPU directly), and the frontend in Docker.

### 2a. Serve an open instruct model with vLLM

```bash
# 192GB HBM3 comfortably serves a large model at long context.
vllm serve Qwen/Qwen2.5-32B-Instruct \
  --port 8001 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.85 &
# wait for "Uvicorn running on http://0.0.0.0:8001"
curl -s http://localhost:8001/v1/models | jq .data[].id
```

### 2b. Run the backend on the host (ROCm torch from the image)

```bash
pip install fastapi "uvicorn[standard]" pydantic httpx   # torch already present
export SIM_BACKEND=vllm
export VLLM_ENDPOINT=http://localhost:8001/v1
export SEED_MODE=false                 # LIVE mode: real GDACS/USGS
export FIREWORKS_API_KEY=...            # optional, for P1 briefings
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Confirm the GPU is seen and the fallback banner is OFF:

```bash
curl -s localhost:8000/api/health/gpu   # device should be "AMD Instinct MI300X"
curl -s localhost:8000/api/status       # sim_backend_degraded: false
```

### 2c. Frontend

```bash
# point nginx proxy at the host backend, or just build+serve statically:
docker compose up --build frontend
# open http://<droplet-ip>:3000
```

> The Monte Carlo engine and the embedding dedup are device-agnostic
> (`# ROCM:` comments in `monte_carlo.py`, `embeddings.py`) — they use the
> ROCm GPU automatically once torch sees it. No code change between laptop
> and droplet.

---

## 3. Evidence capture (fills the pitch metrics table)

Run these on the droplet with the GPU live, save the output.

```bash
# 3.1 Monte Carlo GPU-vs-CPU speedup (the headline number)
python scripts/benchmark.py --runs 10000 50000 100000
#     -> evidence/benchmark.json  (CPU ms vs MI300X ms, speedup, runs/sec)

# 3.2 vLLM throughput on the batched 3-branch scenario call
#     watch tokens/sec in the vllm serve logs while running a simulation:
curl -s -X POST "localhost:8000/api/events/seed-FL-001/simulate?horizon=24h" >/dev/null

# 3.3 Peak VRAM with everything resident (the 192GB story)
rocm-smi --showmeminfo vram        # during a simulation with vLLM loaded

# 3.4 Ingest-to-globe latency for a live event: note the timestamp a GDACS
#     event appears in /api/events vs its fromdate.
```

Record a screen capture of the bottom GPU readout spiking during a
simulation — visible AMD usage is judged AMD usage.

### Metrics table to fill (ARCHITECTURE.md §9)

| Metric | Source | Value |
|---|---|---|
| Monte Carlo 100k runs, CPU → MI300X | `benchmark.py` | ___ ms → ___ ms (__×) |
| Scenario agent, 3 branches batched | vLLM logs | ___ tokens/sec |
| Peak VRAM (vLLM + MC + embeddings) | `rocm-smi` | ___ / 192 GB |
| Ingest-to-globe latency (live GDACS) | manual | ___ s |

---

## 4. Three clean runs + backup video (Day 6 exit)

1. Run the full demo flow (Mode A→B→C) three times without intervention.
2. Record the backup demo video (non-negotiable — Wi-Fi insurance).
3. **Stop the droplet.**

---

## 5. Failure fallbacks (rehearsed, not theoretical)

| If… | Then |
|---|---|
| vLLM won't serve the model | `export SIM_BACKEND=fireworks` — options still generate |
| No Fireworks key / API down | options degrade to grounded templates; briefings to raw-data |
| Live feeds flaky at judging | `export SEED_MODE=true` — the rehearsed offline demo |
| Droplet unreachable entirely | play the backup video |

Run `python scripts/failure_drills.py` after any config change to confirm the
degradations still hold.
