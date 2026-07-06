"""Fireworks AI backend accessor (also AMD-powered infra).

Per CLAUDE.md the LLM layer is ONE OpenAI-compatible wrapper with two
configs; the wrapper lives in `backend.llm.client`. This module is the named
entry point for the Fireworks config used by P1 briefings and as the scenario
fallback backend.
"""

from backend.llm.client import get_briefing_client as get_fireworks_client

__all__ = ["get_fireworks_client"]
