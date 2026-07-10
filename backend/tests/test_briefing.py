"""Briefing writer: validation, repair retry, raw-data fallback, caching."""

import asyncio
import json

from backend import cache
from backend.briefing.writer import write_briefing
from backend.llm.client import LLMUnavailable
from backend.models import Briefing
from backend.tests.conftest import FakeLLM
from scripts.seed_events import load_seed_events

EVENTS = {e.id: e for e in load_seed_events()}
JAKARTA = EVENTS["seed-FL-001"]


def _good_brief_json() -> str:
    return json.dumps({
        "headline": "Flooding reported across Greater Jakarta",
        "summary": "A flood event is affecting low-lying districts. " * 6,
        "confirmed_facts": ["Flood reported", "Jakarta affected", "Source SEED"],
        "key_unknowns": ["Casualty figures unconfirmed", "Response status unknown"],
        "watch_indicators": ["Rising river gauges", "Upstream dam releases"],
    })


class TestBriefingHappyPath:
    def test_valid_response_parsed(self):
        fake = FakeLLM(responses=[_good_brief_json()])
        b = asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=False))
        assert isinstance(b, Briefing)
        assert "Jakarta" in b.headline


class TestBriefingRepair:
    def test_bad_then_repaired(self):
        fake = FakeLLM(responses=["garbage", _good_brief_json()])
        b = asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=False))
        assert isinstance(b, Briefing)
        assert fake.calls == 2


class TestBriefingFallback:
    def test_unavailable_backend_gives_rawdata_brief(self):
        fake = FakeLLM(raise_exc=LLMUnavailable("no key"))
        b = asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=False))
        assert isinstance(b, Briefing)
        # Fallback brief states only facts from the event data.
        assert JAKARTA.country in b.summary
        assert b.confirmed_facts

    def test_both_attempts_bad_falls_back(self):
        fake = FakeLLM(responses=["nope", "still nope"])
        b = asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=False))
        assert isinstance(b, Briefing)  # raw-data fallback, not an exception

    def test_fallback_is_never_cached(self, tmp_path, monkeypatch):
        """A degraded brief must not persist: the on-disk cache survives
        restarts, so caching it would keep serving 'model unavailable' long
        after the API key is fixed."""
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
        cache._MEM.clear()

        down = FakeLLM(raise_exc=LLMUnavailable("no key"))
        first = asyncio.run(write_briefing(JAKARTA, client=down, use_cache=True))
        assert "fallback brief" in first.summary

        # Backend recovers: the very next call must reach the LLM, not the cache.
        up = FakeLLM(responses=[_good_brief_json()])
        second = asyncio.run(write_briefing(JAKARTA, client=up, use_cache=True))
        assert up.calls == 1
        assert "fallback brief" not in second.summary

        # A good brief, by contrast, IS cached.
        third = asyncio.run(write_briefing(JAKARTA, client=up, use_cache=True))
        assert up.calls == 1
        assert third.headline == second.headline


class TestBriefingCache:
    def test_second_call_hits_cache_and_skips_llm(self):
        fake = FakeLLM(responses=[_good_brief_json()])
        first = asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=True))
        # A cache hit must not consult the client again (would raise: empty queue).
        second = asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=True))
        assert first == second
        assert fake.calls == 1

    def test_cache_survives_memory_clear_via_disk(self):
        fake = FakeLLM(responses=[_good_brief_json()])
        asyncio.run(write_briefing(JAKARTA, client=fake, use_cache=True))
        cache.clear_memory()  # simulate a process restart
        fake2 = FakeLLM(raise_exc=AssertionError("should not be called"))
        again = asyncio.run(write_briefing(JAKARTA, client=fake2, use_cache=True))
        assert isinstance(again, Briefing)
