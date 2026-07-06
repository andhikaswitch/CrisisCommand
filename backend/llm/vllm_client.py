"""Local vLLM (MI300X) backend accessor.

Per CLAUDE.md the LLM layer is ONE OpenAI-compatible wrapper with two
configs; the wrapper lives in `backend.llm.client`. This module is the named
entry point for the vLLM config that serves batched P2/P3 scenario calls on
the droplet (SIM_BACKEND=vllm), with automatic Fireworks fallback.
"""

from backend.llm.client import get_scenario_client as get_vllm_client

__all__ = ["get_vllm_client"]
