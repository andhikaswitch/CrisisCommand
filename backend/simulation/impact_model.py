"""Vetted mitigation factors and impact estimators.

PROMPTS.md rule: the LLM may only apply THESE factors to Monte Carlo ranges —
it never invents quantitative outcomes. Each factor is a (low, high)
multiplier on exposed population, with its provenance stated. Values marked
HEURISTIC are team judgment calls, clearly flagged; the rest lean on
published disaster-response findings (effect directions and magnitudes are
coarse by design — wide ranges over false precision).

Cost/response-time estimators land on Day 2 alongside the scenario agent.
"""

# (low, high) multipliers applied to the baseline exposed-population range.
MITIGATION_FACTORS: dict[str, tuple[float, float]] = {
    # Timely staged evacuation of mapped zones. Literature on flood/cyclone
    # evacuations (e.g., post-Haiyan reviews) shows well-executed early
    # evacuation removes the majority of at-risk population from exposure.
    "timely_staged_evacuation": (0.25, 0.45),
    # Pre-positioned supplies/shelters reduce effective exposure (people
    # reached vs stranded), not the hazard itself. HEURISTIC.
    "prepositioned_supplies": (0.60, 0.80),
    # Early-warning dissemination without movement orders. HEURISTIC.
    "early_warning_broadcast": (0.70, 0.90),
    # Monitoring-only posture changes nothing about exposure by itself;
    # its value is optionality. Identity multiplier keeps arithmetic honest.
    "enhanced_monitoring": (0.95, 1.00),
}
