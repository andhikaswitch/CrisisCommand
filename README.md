# 🌍 CrisisCommand

**Dashboards show you the crisis. CrisisCommand simulates your decision.**

An AI war room for crisis leaders, built for the AMD Developer Hackathon: ACT II (Unicorn Track) by team **Imitasi**. Live disaster and tension data flows onto a holographic 3D Earth; for any crisis, an AI simulation engine forecasts escalation and presents three grounded response options — with honest numbers, ranges, and trade-offs.

## The Gap

Commercial situational-awareness tools (Crisis24, Dataminr) and public dashboards (GDACS, ReliefWeb) tell decision-makers *what is happening*. None of them simulate *what happens next under each possible response*. That decision layer — the hard part — is what CrisisCommand builds, and no open-source equivalent exists.

## Why AMD (Engineered In, Not Bolted On)

- **Self-hosted LLM on the AMD GPU via vLLM** — scenario-branch reasoning runs batched on the AMD GPU; large HBM keeps the LLM, Monte Carlo engine, and embedding pipeline resident simultaneously
- **GPU Monte Carlo engine (PyTorch/ROCm)** — 10,000 stochastic hazard-exposure simulations as one tensor batch; measured CPU-vs-GPU speedup shown live in the UI
- **Fireworks AI** (itself AMD-powered) handles quality-critical situation briefings
- A live GPU utilization readout sits in the interface — AMD usage you can *see* during the demo

Device-agnostic by construction: ROCm presents as `cuda`, and every readout
names whatever card the backend self-reports — and when ROCm returns no
marketing name (it does on some cards), we show the architecture instead, e.g.
`AMD GPU (gfx1100)`. No GPU model is hardcoded anywhere, so the demo always
tells the truth about the hardware it actually ran on.

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
python -m pytest                   # 153 tests
python scripts/smoke_test.py       # end-to-end: seed → Monte Carlo → 3 options
python scripts/failure_drills.py   # 5 induced-failure drills
```

### AMD ROCm notebook — the GPU demo, end to end

Tested on the AMD Radeon developer notebook portal
(`radeon-global.anruicloud.com`, ROCm 7.2 + vLLM + PyTorch 2.9 image). Request a
notebook, open a **Terminal**, then run the four blocks below. Each one fixes a
real trap that will otherwise cost you an hour.

**1. Trust the AMD TLS proxy — deliberately.** The environment intercepts TLS to
GitHub/Docker/HuggingFace with a self-signed cert
(`AMD_ONECLICK_OPENCODE_TLS_PROXY`), so `git clone` fails with
`server certificate verification failed` and even `certifi` is rejected.

```bash
curl -sO https://raw.githubusercontent.com/andhikaswitch/CrisisCommand/main/scripts/trust_amd_proxy.sh
bash trust_amd_proxy.sh          # inspect it first; it asks before trusting
```

The script prints the certificate's subject, issuer and SHA-256 fingerprint,
then **refuses** unless it is genuinely the AMD proxy (self-signed *and* named
`Proxy Certificate for GitHub/Docker/HuggingFace`), and scopes the trust to
`https://github.com/` only. Pass `--system` if `pip`/`curl`/`apt` also need the
proxy.

> ⚠ **Run this only inside the AMD notebook, never on your laptop.** The
> tempting one-liner — `openssl s_client … > /usr/local/share/ca-certificates/`
> then `update-ca-certificates` — trusts *whatever* certificate is presented, as
> a system-wide root CA. On a hostile network that hands an attacker the ability
> to impersonate every site, permanently. The script exists to make that failure
> mode impossible to hit by accident.
>
> Also: the proxy can read the traffic it terminates. **Never `git push` from the
> notebook** — that sends your GitHub token through it. Copy
> `evidence/benchmark.json` out and commit it from your own machine.

**2. Use the preinstalled ROCm PyTorch.** It lives in `/opt/venv`, *not* in the
system Python, so `import torch` fails until you activate it:

```bash
git clone https://github.com/andhikaswitch/CrisisCommand.git
cd CrisisCommand
source /opt/venv/bin/activate
python -c "import torch; print(torch.version.hip, torch.cuda.is_available())"   # 7.2.x True
```

> **Never run `pip install torch` here.** PyPI would replace the ROCm build with
> the CUDA wheel, and the app would silently fall back to CPU with no error.
> `requirements.txt` deliberately excludes torch for this reason.

**3. Configure and launch.** One command does deps → tests → benchmark → serve →
public URL:

```bash
cat > .env <<'EOF'
FIREWORKS_API_KEY=fw_your_key_here
FIREWORKS_MODEL=accounts/fireworks/models/gpt-oss-120b
SIM_BACKEND=fireworks
SEED_MODE=false
EOF

bash scripts/notebook_bootstrap.sh --tunnel
```

It prints a `https://<random>.trycloudflare.com` URL. Open it from your laptop —
the notebook only ever runs the server; the 3D globe renders in your browser,
and the backend serves the UI, REST and WebSocket from one origin (no CORS, one
tunnel). Leave that terminal running; `cloudflared` holds the tunnel open.

**4. Read the footer.** It must name the card. On our allocation ROCm reported an
*empty* device name (gfx1100 / libdrm), so `backend/device.py` falls back to the
architecture and shows `AMD GPU (gfx1100) · 48 GB`. We never hardcode a GPU
model — see [CLAUDE.md](CLAUDE.md).

**Measured there** (`evidence/benchmark.json`, 48 GB gfx1100, ROCm 7.2):

| Monte Carlo runs | CPU | AMD GPU | Speedup |
|---|---|---|---|
| 10,000 | 15.5 ms | 1.3 ms | 11.9× |
| 50,000 | 73.3 ms | 1.9 ms | 39.5× |
| 100,000 | 201.1 ms | 3.3 ms | **61.2×** (30.4M runs/sec) |

The speedup *widening* with batch size is the point: it shows the kernel is
genuinely one batched tensor op, not a disguised Python loop.

**Stop the notebook when done** — the tunnel is unauthenticated and GPU time is
capped. Full runbook, including the vLLM path and the three deployment
topologies: **[DEPLOY.md](DEPLOY.md)**.

### Other AMD GPU hosts + live mode

`SEED_MODE=false` for live feeds; `SIM_BACKEND=vllm` with
`vllm serve <model> --port 8001` for the on-GPU scenario agent. If vLLM is
unreachable the app degrades to Fireworks and says so in the UI.

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

**Imitasi** — Built with AMD GPUs · ROCm · vLLM · Fireworks AI · PyTorch · FastAPI · React · Three.js
