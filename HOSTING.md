# HOSTING.md — the always-on "Application URL" for the submission form

## The problem this solves

The submission form wants an **Application URL** judges can click any time, for
days. The Cloudflare tunnel from the ROCm notebook cannot be that URL:

- it changes every restart and dies when the notebook session ends;
- the notebook itself auto-stops (GPU quota is 6h/24h);
- it is unauthenticated and must not be left running.

So we split two concerns that were tangled together:

| Need | Where it lives |
|---|---|
| A clickable URL that is always up | **Hugging Face Spaces (CPU)** — this file |
| Proof the AMD GPU did the work | the demo **video** + `evidence/benchmark.json` |

The app runs fine on CPU (`get_device()` falls back automatically). The only
thing the CPU host loses is the live GPU readout in the footer, which reads
`cpu` instead of `AMD GPU (gfx1100)`. That is fine: the GPU story is already
captured, measured, and committed.

## Host choice: NOT Hugging Face

HF Spaces made Docker and Gradio SDKs **paid** (2026); only Static (HTML/JS) is
free, and Static cannot run this Python backend. So HF is out. Use a host whose
free tier runs a container.

Measured footprint (a real container, SEED mode): **166 MB idle, 170 MB during a
10k-run simulation.** So a 512 MB free tier is comfortable. torch is CPU-only and
lazy-loads.

**Recommended: Render.com** (free web service, Docker, WebSocket, no credit card
for the free tier). Spins down after ~15 min idle and wakes on the next request
(~30-50s). **Backup: Koyeb** (free tier, Docker, one service).

> Free-tier terms change often. If Render now asks for a card, try Koyeb; the
> same Dockerfile works on both because it binds to the injected `$PORT`.

## Deploy to Render (from your laptop, ~10 minutes)

**1.** Sign in at <https://render.com> with your GitHub account.

**2.** New → **Web Service** → connect the `CrisisCommand` repo.

**3.** Render detects the root `Dockerfile` automatically. Settings:
- Runtime: **Docker**
- Instance type: **Free**
- No start command needed (the Dockerfile's `CMD` binds `$PORT`).

**4.** (Optional, for live events + AI briefings) → **Environment** → add:

| Key | Value |
|---|---|
| `FIREWORKS_API_KEY` | your `fw_...` key |
| `FIREWORKS_MODEL` | `accounts/fireworks/models/gpt-oss-120b` |
| `SEED_MODE` | `false` |

Without the key it still runs; briefings just show the raw-data template. Omit
`SEED_MODE` (or set `true`) to run the always-works offline demo on 15 curated
events.

**5.** Create Web Service. Watch the build log. Your URL will be:

```
https://crisiscommand.onrender.com          (or the name Render assigns)
```

## Koyeb fallback (if Render wants a card)

<https://app.koyeb.com> → Create Service → **Docker** or **GitHub** →
select the repo → Koyeb reads the `Dockerfile` → Free instance → Deploy. Add the
same env vars under the service's Environment tab. URL: `https://<app>.koyeb.app`.

## What each form field gets

| Field | Value |
|---|---|
| Public GitHub Repository | `https://github.com/andhikaswitch/CrisisCommand` |
| Demo Application Platform | `Render` (or `Koyeb`) |
| Application URL | the `https://...onrender.com` URL Render gives you |

## Notes

- **First load after idle** takes ~30-50s while the free instance wakes. Open it
  once yourself right before you submit so it is warm when a judge clicks.
- **Redeploy after a code change:** push to GitHub; Render auto-deploys. (Rebuild
  `frontend/dist` first if you changed the UI: `cd frontend && npm run build`.)
- Render/Koyeb and the ROCm notebook are unrelated. The notebook only records the
  GPU demo video; this host is the permanent public URL, on CPU.
