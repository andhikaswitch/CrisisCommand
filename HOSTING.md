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

## Reality in 2026: free container hosts all want a credit card

HF Spaces made Docker paid; Render asks for a card ($1 auth); Koyeb went
Pro-only at $29/mo. So the "always-on container" path is not card-free anymore.

Two options remain:

- **A. Static showcase (card-free, no account needed) — recommended for the
  submission URL.** A pre-baked version of the app on a static host. See below.
- **B. Container host with a card**, if you are willing to add one (the auth is
  not charged). Use the Dockerfile as-is; it binds `$PORT`. Skip to
  "Container host" at the bottom.

---

## A. Static showcase → Vercel (recommended, no card)

The app is normally frontend + Python backend. For a permanent free URL we bake
the backend's responses (events, simulations, AI briefings) into static JSON
(committed under `frontend/public/demo-data/`) and build a frontend that reads
them. It shows the real product — globe, briefings, simulation, three options —
with a banner noting the live/GPU version is in the video.

`vercel.json` already wires this up. The demo data is committed, so Vercel needs
no Fireworks key at build time.

**Deploy on Vercel (auto-builds from GitHub):**
1. <https://vercel.com> → sign in with GitHub.
2. **Add New → Project** → import `CrisisCommand`.
3. Do not change anything — `vercel.json` sets the build command
   (`VITE_DEMO_DATA=1`) and output directory.
4. **Deploy.** URL: `https://crisiscommand-<hash>.vercel.app`. Every push
   auto-redeploys. Free, no card.

**Regenerating the baked data** (only if the seed events or briefings change —
needs your Fireworks key in `.env` for real AI briefings):

```bash
python scripts/bake_demo_data.py        # writes frontend/public/demo-data/*.json
git add frontend/public/demo-data && git commit -m "refresh demo data" && git push
```

> What the showcase does NOT do: live feeds (needs the backend) and real-time
> on-GPU simulation. Those are in the demo video. Clicking a drill still shows a
> real baked simulation and a real AI briefing, so the product is fully legible.
> Use the **DRILLS** or **ALL** filter — the **LIVE** filter is empty here by
> design (no backend feed on a static host).

**Netlify / Cloudflare Pages alternative:** run the two commands above plus
`cd frontend && VITE_DEMO_DATA=1 npm run build`, then drag `frontend/dist` onto
<https://app.netlify.com/drop> (no account, no card).

## What each form field gets (static showcase)

| Field | Value |
|---|---|
| Public GitHub Repository | `https://github.com/andhikaswitch/CrisisCommand` |
| Demo Application Platform | `Vercel` (static) |
| Application URL | the `https://...vercel.app` URL |

---

## B. Container host (only if you will add a card)

Measured footprint (real container, SEED mode): **166 MB idle, 170 MB during a
10k-run simulation** — any 512 MB tier fits. The Dockerfile binds `$PORT`, so
Render / Koyeb / Cloud Run all work. Add `FIREWORKS_API_KEY`, `FIREWORKS_MODEL`,
`SEED_MODE=false` as env vars. This path gives the full live app (real feeds,
real-time simulation) at the cost of a card on file.

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
