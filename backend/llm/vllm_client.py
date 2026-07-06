"""OpenAI-compatible client for the local vLLM server on the MI300X — Day 2.

Speaks to VLLM_ENDPOINT (default http://localhost:8001/v1). Shares its
request/validation wrapper with fireworks_client; backend is selected by
SIM_BACKEND=vllm|fireworks with automatic fallback (ARCHITECTURE.md §8).
"""
