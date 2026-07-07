"""Deliberate failure drills (Day 5 hardening).

Induces each failure the judges (or a bad conference network) could throw at
the app and asserts it degrades gracefully instead of crashing:

  1. feed down            — ingestor fetch fails → store untouched, source
                            marked error, other sources unaffected
  2. vLLM/LLM unreachable — simulation still returns 3 template options
  3. invalid LLM JSON     — briefing repair path → raw-data fallback
  4. mid-sim WS reconnect — a dropped WS client does not break the broadcast
  5. simulate live event  — no population_context → honest 422, not a crash

Run:  python scripts/failure_drills.py
Exit code 0 = every failure handled. Non-zero = a drill regressed.
"""

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx  # noqa: E402

from backend.briefing.writer import write_briefing  # noqa: E402
from backend.ingest import normalizer  # noqa: E402
from backend.ingest.store import EventStore  # noqa: E402
from backend.llm.client import LLMUnavailable  # noqa: E402
from backend.simulation.orchestrator import run_full_simulation  # noqa: E402
from scripts.seed_events import load_seed_events  # noqa: E402

PASS, FAIL = "[OK]", "[XX]"
_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {PASS if ok else FAIL} {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


class _RaisingClient:
    """Stands in for an LLM client whose backend is unreachable."""

    async def chat(self, *a, **k):
        raise LLMUnavailable("induced: backend down")


class _BadJSONClient:
    async def chat(self, *a, **k):
        return "the model rambled and produced no JSON whatsoever"


async def drill_feed_down() -> None:
    print("[1] feed down")
    store = EventStore(seed=True, force_cpu=True)
    before = len(store.snapshot())
    store.add_from_source("GDACS", [], error="induced: connection refused")
    after = len(store.snapshot())
    health = {h.source: h for h in store.source_health()}
    check("store untouched by dead feed", before == after, f"{before} events")
    check("source marked error", health["GDACS"].status() == "error")
    check("seed source still ok", health["SEED"].status() == "ok")


async def drill_llm_down() -> None:
    print("[2] vLLM/LLM unreachable")
    event = next(e for e in load_seed_events() if e.id == "seed-FL-001")
    result = await run_full_simulation(
        event, horizon="24h", n_runs=1000, seed=1,
        client=_RaisingClient(), use_cache=False,
    )
    check("simulation still returns 3 options", len(result.options) == 3)
    check("options are grounded templates",
          all(o.id.endswith("-template") for o in result.options))


async def drill_bad_json() -> None:
    print("[3] invalid LLM JSON")
    event = next(e for e in load_seed_events() if e.id == "seed-EQ-004")
    brief = await write_briefing(event, client=_BadJSONClient(), use_cache=False)
    check("briefing falls back to raw-data brief", brief.headline != "")
    check("fallback states only feed facts", event.country in brief.summary)


async def drill_ws_reconnect() -> None:
    print("[4] mid-sim WS client drop")
    from backend.ws import ConnectionManager

    mgr = ConnectionManager()

    class _DeadWS:
        async def send_json(self, _):
            raise RuntimeError("client vanished")

    mgr._clients.add(_DeadWS())  # a client that fails on send
    try:
        await mgr.broadcast({"type": "sim_progress", "runs_done": 1})
        ok = mgr.client_count == 0  # dead client pruned, no exception
    except Exception:
        ok = False
    check("broadcast prunes dead client without raising", ok)


async def drill_simulate_live_event() -> None:
    print("[5] simulate a live event with no exposure context")
    live = normalizer.make_event(
        id="usgs-live-x", kind="earthquake", title="M6.6 offshore",
        lat=38.0, lon=142.0, country="Japan", severity=0.6,
        started_at=normalizer.parse_iso_utc("2024-07-01T00:00:00Z"),
        source="USGS", source_url="https://example.org", raw={},
    )
    raised = False
    try:
        await run_full_simulation(live, horizon="24h", n_runs=500, use_cache=False)
    except ValueError:
        raised = True  # refuses to invent an exposure base (honesty rule)
    check("refuses to simulate without population_context", raised)


async def main() -> int:
    for drill in (
        drill_feed_down, drill_llm_down, drill_bad_json,
        drill_ws_reconnect, drill_simulate_live_event,
    ):
        await drill()
    print()
    if _failures:
        print(f"FAILURE DRILLS FAILED: {', '.join(_failures)}")
        return 1
    print("ALL FAILURE DRILLS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
