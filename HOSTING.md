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

## Why Hugging Face Spaces

Free forever, Docker + WebSocket support, stays up independently of your laptop
or the notebook, and you already have an HF account. The root `Dockerfile`
serves the API, the WebSocket, and the built SPA from one port (7860, the HF
default), so no extra config is needed.

## Deploy (from your laptop, ~10 minutes)

**1. Create the Space** at <https://huggingface.co/new-space>:
- Owner: your account
- Space name: `crisiscommand`
- License: choose any (e.g. MIT)
- **Space SDK: Docker** → **Blank**
- Visibility: **Public**

**2. Push the code to the Space.** HF gives the Space its own git repo. From the
project root:

```bash
# one-time: install git-lfs if you haven't (frontend/dist + PDF are binary)
git lfs install

git remote add space https://huggingface.co/spaces/<your-hf-user>/crisiscommand
git push space main
```

If prompted for a password, use a **Hugging Face access token** (Settings →
Access Tokens → New token, role `write`), not your HF password.

HF auto-detects the Docker SDK from the root `Dockerfile` and starts building.
Watch the build log in the Space's UI.

**3. Turn on live mode + AI briefings (optional but recommended).** In the Space:
**Settings → Variables and secrets**:

| Add as | Name | Value |
|---|---|---|
| Secret | `FIREWORKS_API_KEY` | your `fw_...` key |
| Variable | `FIREWORKS_MODEL` | `accounts/fireworks/models/gpt-oss-120b` |
| Variable | `SEED_MODE` | `false` |

Without the key it still runs, but briefings show the raw-data template. With
`SEED_MODE=false` the globe shows real live events plus the 15 curated drills.

**4. Your Application URL** is then:

```
https://<your-hf-user>-crisiscommand.hf.space
```

That is what goes in the form. It survives your laptop being off.

## What each form field gets

| Field | Value |
|---|---|
| Public GitHub Repository | `https://github.com/andhikaswitch/CrisisCommand` |
| Demo Application Platform | `Hugging Face Spaces (Docker)` |
| Application URL | `https://<your-hf-user>-crisiscommand.hf.space` |

## Notes

- **First load after idle** takes ~20-30s while the Space wakes. Open it once
  yourself before you submit, so it is warm when a judge clicks.
- **Redeploy after a code change:** `git push space main` again.
- The HF Space and the notebook are unrelated. The notebook is only for
  recording the GPU demo video; the Space is the permanent public URL.
- If you would rather not run live feeds on a public host, set `SEED_MODE=true`
  (or omit it — that is the default). The full demo still works offline against
  the 15 curated events.
