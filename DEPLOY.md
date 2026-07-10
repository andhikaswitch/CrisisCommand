# DEPLOY.md — CrisisCommand on AMD GPUs

Turnkey runbook for full deployment + evidence capture. Three tiers: the
**default seed demo** runs anywhere with Docker; the **Fireworks step** turns
on real AI briefings in five minutes; the **AMD GPU path** adds the ROCm
compute and vLLM serving that is the AMD story.

No GPU model is assumed anywhere — MI300X, MI250, MI210 all work, and every
readout names the card the code actually ran on (see backend/device.py — some
ROCm cards report an empty name, so we fall back to the gfx architecture).

Cost discipline: **stop the droplet / notebook when idle**, cache
aggressively, the credit clock is real. Nothing below leaves a GPU running
longer than the capture needs.

---

## 0. Prerequisites

- An AMD GPU environment — either the AMD Developer Cloud **GPU droplet**
  (vLLM Quick Start image) or the **ROCm Jupyter notebook** (ROCm + vLLM +
  PyTorch preinstalled). Both satisfy the Unicorn Track.
- Repo cloned there; Docker + Docker Compose available (droplet only).
- `FIREWORKS_API_KEY` for the P1 briefings — without it the app silently
  falls back to a raw-data template brief that literally says so in the UI.

---

## 0.5 Fireworks key (5 minutes, no GPU needed — do this first)

The single highest-value step: without it, every briefing in the demo reads
*"automated fallback brief … the briefing model was unavailable"*.

```bash
cp .env.example .env                       # if you haven't already
# edit .env:  FIREWORKS_API_KEY=fw_...     (from fireworks.ai → API Keys)

python scripts/check_fireworks.py          # lists models your account can serve
python scripts/check_fireworks.py --test   # live call: PASS means briefings are real
```

**Never guess a model ID** — Fireworks retires serverless models, so the
`FIREWORKS_MODEL` shipped in `.env.example` may already be gone. `check_fireworks.py`
asks the account and flags a mismatch. Copy an ID it prints into `.env`:

```bash
FIREWORKS_MODEL=accounts/fireworks/models/<id-from-the-list>
```

Choosing: briefings (P1) and policy options (P2) are low-volume and
quality-critical, and must emit strict JSON that survives schema validation.
Pick a large general instruct model over a code- or vision-specialised one.
Cost is negligible at demo volume (a few hundred tokens per briefing), so
optimise for instruction-following, not price. Restart the backend after
editing `.env`, then confirm the fallback text is gone:

```bash
curl -s localhost:8000/api/status | grep briefing   # "fireworks", not "template"
```

---

## 0.6 ROCm Jupyter notebook path (no droplet required)

The notebook gives you a GPU shell — everything below runs in notebook cells
(`!` prefix) or a terminal tab. Budget your session: the GPU time cap is real,
and step 2 alone produces the pitch's headline number.

```python
# cell 1 — get the code and confirm which card you were allocated
!git clone <your-repo-url> crisiscommand && cd crisiscommand
!python -c "from backend.device import device_label; print(device_label())"
```

That printed name is what the UI and the pitch will say. Do not override it.

```python
# cell 2 — deps. torch/vllm are PREINSTALLED: never pip install torch here,
# it would drag in the CUDA build and break ROCm.
!pip install fastapi "uvicorn[standard]" pydantic httpx pytest
!python -m pytest -q                         # 140 tests, GPU ones now un-skip
```

```python
# cell 3 — THE EVIDENCE. Writes evidence/benchmark.json (CPU vs GPU, measured).
# This artifact outlives the session: capture it even if you do nothing else.
!python scripts/benchmark.py --runs 10000 50000 100000
```

```python
# cell 4 (optional, the deepest AMD story) — serve the scenario model on-GPU
!nohup vllm serve <open-instruct-model> --port 8001 --max-model-len 8192 &
# then run the backend against it:
!SIM_BACKEND=vllm VLLM_ENDPOINT=http://localhost:8001/v1 \
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

`SIM_BACKEND=vllm` degrades honestly: if vLLM is not reachable the app routes
scenario calls to Fireworks and the UI shows a `FIREWORKS (FALLBACK)` banner
rather than pretending. Verify the GPU is really being used:

```bash
curl -s localhost:8000/api/health/gpu   # device = the card, not "cpu"
```

---

## 0.7 Which "localhost"? — networking in a remote notebook

The single confusing part of a cloud notebook: **`localhost` means the notebook
machine, not your laptop.** Two very different needs follow.

**Fireworks needs nothing.** It is an *outbound* HTTPS call authenticated by the
key. Anywhere with internet — laptop, droplet, notebook — works identically.
There is no port to open and no tunnel to build. Put `FIREWORKS_API_KEY` in a
`.env` on whatever machine runs the backend (never commit it) and you are done.

**vLLM and the web UI are the opposite: they need *inbound* reach.** `vllm serve`
listens on the notebook's `localhost:8001`; your laptop browser cannot see it.
Pick a topology:

| | Where backend runs | Monte Carlo on | vLLM | What judges see |
|---|---|---|---|---|
| **A. All-on-GPU** | notebook | **AMD GPU** | local `localhost:8001` | full AMD story; needs a tunnel to view the UI |
| **B. Split** | laptop | laptop CPU | notebook, via tunnel | GPU readout says CPU — weakens the story |
| **C. Evidence-only** | laptop | laptop CPU | not served | fastest; AMD story rests on `benchmark.json` |

**A is the one worth doing**, because the backend sits next to the GPU: the
Monte Carlo readout names the real card, and `VLLM_ENDPOINT=http://localhost:8001/v1`
resolves on that same machine — no tunnel needed *between* backend and vLLM.
Only the browser needs a way in:

```python
# in the notebook, after backend is up on :8000
!curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
!chmod +x cloudflared && ./cloudflared tunnel --url http://localhost:8000
# prints https://<random>.trycloudflare.com  -> open it from your laptop
```

Serve the built frontend from that same origin (`npm run build`, then let the
backend or any static server host `frontend/dist`) so `/api` and `/ws` stay
same-origin and no CORS work is needed.

**C is the safe fallback** and costs almost no GPU time: run `benchmark.py`,
download `evidence/benchmark.json`, demo locally against Fireworks. The AMD
claim is then a measured artifact rather than a live readout — honest, and it
survives a dead conference Wi-Fi.

In topology B, point the laptop backend at the tunnelled vLLM:

```bash
SIM_BACKEND=vllm VLLM_ENDPOINT=https://<random>.trycloudflare.com/v1 \
  uvicorn backend.main:app --port 8000
```

`VLLM_ENDPOINT` is just a base URL — any scheme/host works, and `VLLM_API_KEY`
is available if you put auth in front of the tunnel. **Never expose a tunnel to
an unauthenticated vLLM for longer than the demo**: it is an open LLM endpoint
on the public internet.

---

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

## 2. AMD GPU path (the AMD showcase)

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
curl -s localhost:8000/api/health/gpu   # device = the card, never "cpu"
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
| Monte Carlo 100k runs, CPU → AMD GPU | `benchmark.py` | 201.1 ms → 3.3 ms (61.2×) on gfx1100 |
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
