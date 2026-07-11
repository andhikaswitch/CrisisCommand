"""Freeze the app's API responses into static JSON for a card-free static host.

Every free container host now demands a credit card (HF Docker, Render, Koyeb
all went paid in 2026). A static host does not: Netlify Drop, Cloudflare Pages
and GitHub Pages serve files for free with no card and no account. But the SPA
needs data. So we bake it once here, and the frontend (built with
VITE_DEMO_DATA=1) reads these files instead of calling a backend.

What gets baked, into frontend/public/demo-data/:
  events.json          - all events: the curated drills PLUS a live snapshot
  status.json          - LIVE-mode status so the HUD renders
  brief-<id>.json      - the AI situation briefing per event (drills AND live)
  sim-<id>.json        - the full simulation (all horizons + 3 options) per drill

Run it with your Fireworks key in .env so the briefings are the real AI ones,
not the template fallback:

    python scripts/bake_demo_data.py

Then build the static bundle and deploy frontend/dist (see HOSTING.md):

    cd frontend && VITE_DEMO_DATA=1 npm run build
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.env import load_dotenv  # noqa: E402

load_dotenv(force=True)  # pick up FIREWORKS_API_KEY for real briefings

from backend.briefing.writer import write_briefing  # noqa: E402
from backend.ingest.store import EventStore  # noqa: E402
from backend.simulation.monte_carlo import SUPPORTED_KINDS, UnsupportedHazardError  # noqa: E402
from backend.simulation.orchestrator import run_full_simulation  # noqa: E402

OUT = _ROOT / "frontend" / "public" / "demo-data"


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {path.relative_to(_ROOT)}")


MAX_LIVE = 60       # snapshot the full live set, not a small sample
BRIEF_CONCURRENCY = 5  # parallel Fireworks calls so 70+ briefings bake in ~2 min


async def _fetch_live():
    """A one-shot snapshot of real live events so the LIVE tab is populated."""
    from backend.ingest import bmkg, flood_risk, gdacs, news, usgs

    sources = [
        ("USGS", usgs.fetch), ("GDACS", gdacs.fetch), ("BMKG", bmkg.fetch),
        ("OPEN-METEO", flood_risk.fetch_global), ("GDELT", news.fetch),
    ]
    out, seen = [], set()
    for name, fetch in sources:
        try:
            got = await fetch()
            fresh = [e for e in got if e.id not in seen]  # GDACS repeats episodes
            seen.update(e.id for e in fresh)
            print(f"  live {name}: {len(fresh)}")
            out.extend(fresh)
        except Exception as exc:  # noqa: BLE001 - a dead feed must not stop the bake
            print(f"  live {name}: skipped ({exc})")
    out.sort(key=lambda e: e.severity, reverse=True)
    return out[:MAX_LIVE]


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    store = EventStore(seed=True)
    drills = store.snapshot()

    print("fetching a live snapshot for the LIVE tab...")
    live = await _fetch_live()
    events = drills + live
    print(f"total baked events: {len(drills)} drills + {len(live)} live")

    _dump(OUT / "events.json", [e.model_dump(mode="json") for e in events])
    _dump(OUT / "status.json", {
        "mode": "LIVE",
        "sim_backend_requested": "fireworks",
        "sim_backend_active": "fireworks",
        "sim_backend_degraded": False,
        "briefing_backend_configured": True,
        "sources": [{"source": s, "status": "ok", "event_count": n,
                     "last_success": None, "last_error": None}
                    for s, n in [("SEED", len(drills)), ("LIVE", len(live))]],
    })

    # Briefings for every event (drills AND live) so any card is clickable.
    # Parallelised with a semaphore so the full snapshot bakes in ~2 min, not 8.
    print(f"baking {len(events)} briefings (concurrency {BRIEF_CONCURRENCY})...")
    sem = asyncio.Semaphore(BRIEF_CONCURRENCY)

    async def _brief(e):
        async with sem:
            brief = await write_briefing(e)
            _dump(OUT / f"brief-{e.id}.json", brief.model_dump(mode="json"))

    await asyncio.gather(*(_brief(e) for e in events))

    # Simulations only for the drills, which have vetted population context.
    print("baking simulations for the drills...")
    for e in events:
        if e.kind in SUPPORTED_KINDS and e.population_context is not None:
            try:
                result = await run_full_simulation(e, horizon="24h", n_runs=10_000)
                _dump(OUT / f"sim-{e.id}.json", result.model_dump(mode="json"))
            except UnsupportedHazardError:
                print(f"  skip sim for {e.id} (unsupported kind)")

    fallback = sum(
        1 for p in OUT.glob("brief-*.json")
        if "fallback brief" in p.read_text(encoding="utf-8")
    )
    if fallback:
        print(f"\nWARNING: {fallback} briefing(s) are the template fallback.")
        print("Set FIREWORKS_API_KEY in .env and re-run for real AI briefings.")
    print(f"\ndone. {len(list(OUT.glob('*.json')))} files in {OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
