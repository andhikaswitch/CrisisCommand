"""Shared test fixtures."""

import pytest

from backend import cache


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the cache at a per-test temp dir and clear the in-process layer.

    Keeps the repo's real .cache clean and stops tests leaking state to
    each other via cached briefings/simulations.
    """
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "cache")
    cache.clear_memory()
    yield
    cache.clear_memory()


class FakeLLM:
    """Duck-typed stand-in for LLMClient — queued responses or a raise."""

    def __init__(self, responses=None, raise_exc=None):
        self._responses = list(responses or [])
        self._raise = raise_exc
        self.calls = 0

    async def chat(self, messages, temperature=0.3, max_tokens=900):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        if not self._responses:
            raise AssertionError("FakeLLM ran out of queued responses")
        return self._responses.pop(0)
