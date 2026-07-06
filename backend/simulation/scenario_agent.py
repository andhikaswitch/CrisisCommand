"""LLM scenario-branch reasoning (vLLM on MI300X) — lands Day 2.

Will take an event + Monte Carlo stats and batch three P2 policy-branch
calls to the local vLLM endpoint (ARCHITECTURE.md §4.2), with validation,
one P-R repair retry, and template-option fallback per branch.
"""
