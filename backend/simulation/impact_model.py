"""Vetted mitigation factors, arithmetic grounding, and template options.

PROMPTS.md rule (the ethical core): the LLM may only apply THESE factors to
Monte Carlo ranges — it never invents quantitative outcomes. We enforce that
here by RECOMPUTING `exposed_population_after` server-side from the factors an
option claims to apply; the LLM's narrative is kept, its numbers are not
trusted. If a branch's LLM call fails entirely, `build_template_option`
produces a fully-grounded option so the simulation never fails.

Each mitigation factor is a (low, high) multiplier on exposed population, with
provenance stated. Values marked HEURISTIC are team judgment calls, clearly
flagged; the rest lean on published disaster-response findings. Ranges are
wide by design — false precision is disqualifying (CLAUDE.md).
"""

from __future__ import annotations

from backend.models import CrisisEvent, GeoZone, HorizonForecast, PolicyOption

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

# Per-branch defaults (index matches PROMPTS.md P2_BRANCH_DIRECTIVES order):
# aggressive / staged / monitor. These drive the template fallback AND the
# server-side cost/time sanity model.
_BRANCH_DEFAULTS = [
    {
        "name": "Immediate staged evacuation",
        "factors": ["timely_staged_evacuation", "early_warning_broadcast"],
        "cost_per_capita_usd": (60, 180),  # transport, shelter, logistics
        "response_time_hours": 6.0,
        "zone_roles": [("evacuation", 1.0), ("hazard", 0.6)],
        "description": (
            "Issue mandatory evacuation for the highest-exposure zones and open "
            "shelters immediately. Local authorities run staged movement outward "
            "from the hazard core while broadcasting warnings on all channels; "
            "responders manage transport and reception."
        ),
        "tradeoffs": [
            "high upfront cost and logistics strain",
            "evacuation fatigue erodes compliance if the hazard underperforms",
            "political fallout if the movement order proves unnecessary",
        ],
    },
    {
        "name": "Pre-position and act on triggers",
        "factors": ["prepositioned_supplies", "early_warning_broadcast"],
        "cost_per_capita_usd": (20, 70),
        "response_time_hours": 18.0,
        "zone_roles": [("staging", 1.2), ("hazard", 0.6)],
        "description": (
            "Move supplies, shelter kits, and responders to staging areas near the "
            "hazard and define trigger conditions (river gauge, wind, shaking "
            "reports) that escalate to evacuation. Warnings go out now; movement "
            "waits on the triggers to avoid premature disruption."
        ),
        "tradeoffs": [
            "residual exposure remains if triggers fire late",
            "staged supplies are a sunk cost if the event does not develop",
            "trigger thresholds are a judgment call under political pressure",
        ],
    },
    {
        "name": "Enhanced monitoring posture",
        "factors": ["enhanced_monitoring"],
        "cost_per_capita_usd": (0, 3),
        "response_time_hours": 1.0,
        "zone_roles": [("hazard", 0.8)],
        "description": (
            "Hold current posture but raise monitoring cadence: dedicated watch "
            "on official feeds, liaison with local agencies, and explicit, "
            "pre-agreed escalation triggers. Lowest cost and least disruption; "
            "buys information, not risk reduction."
        ),
        "tradeoffs": [
            "does not reduce exposure by itself — value is optionality",
            "late escalation forfeits the fastest evacuation windows",
            "public may read inaction as complacency",
        ],
    },
]

# Monitoring carries a fixed operational floor cost regardless of exposure.
_MONITORING_FIXED_COST_USD = (50_000, 250_000)


def compose_factors(keys: list[str]) -> tuple[float, float]:
    """Multiplicatively compose the (low, high) multipliers for given keys.

    Unknown keys are ignored (the prompt only ever sees vetted keys, but we
    stay defensive against LLM drift). No keys -> identity (1.0, 1.0).
    """
    low, high = 1.0, 1.0
    for k in keys:
        if k in MITIGATION_FACTORS:
            f_low, f_high = MITIGATION_FACTORS[k]
            low *= f_low
            high *= f_high
    return low, high


def ground_exposed_after(
    baseline: tuple[int, int], factor_keys: list[str]
) -> tuple[int, int]:
    """Recompute exposed-population-after as pure arithmetic on the baseline.

    after = baseline × composed factor range. This is the number the UI shows
    — never a value the LLM produced. Result stays within [0, baseline].
    """
    p10, p90 = baseline
    low, high = compose_factors(factor_keys)
    after_p10 = min(int(round(p10 * low)), p10)
    after_p90 = min(int(round(p90 * high)), p90)
    after_p10 = max(0, min(after_p10, after_p90))
    return after_p10, after_p90


def estimate_cost(
    baseline: tuple[int, int], branch_index: int
) -> tuple[int, int]:
    """Order-of-magnitude cost from exposed population and action scale.

    Cost is NOT a Monte Carlo output; it is a coarse operational estimate,
    intentionally wide. Monitoring uses a fixed operational floor.
    """
    defaults = _BRANCH_DEFAULTS[branch_index]
    if defaults["factors"] == ["enhanced_monitoring"]:
        return _MONITORING_FIXED_COST_USD
    p10, p90 = baseline
    lo_pc, hi_pc = defaults["cost_per_capita_usd"]
    return int(p10 * lo_pc), int(p90 * hi_pc)


def _severity_radius_km(event: CrisisEvent, base: float) -> float:
    # Hazard footprint scales with severity; coarse but geographically plausible.
    return round((10.0 + 90.0 * event.severity) * base, 1)


def default_zones(event: CrisisEvent, branch_index: int) -> list[GeoZone]:
    zones: list[GeoZone] = []
    for role, scale in _BRANCH_DEFAULTS[branch_index]["zone_roles"]:
        zones.append(
            GeoZone(
                lat=event.lat,
                lon=event.lon,
                radius_km=_severity_radius_km(event, scale),
                role=role,  # type: ignore[arg-type]
            )
        )
    return zones


def build_template_option(
    event: CrisisEvent,
    forecast: HorizonForecast,
    branch_index: int,
) -> PolicyOption:
    """Fully-grounded fallback option (P2 failure -> template, PROMPTS.md P-R).

    Uses only vetted factors and server-side arithmetic; safe to show.
    """
    d = _BRANCH_DEFAULTS[branch_index]
    baseline = forecast.exposed_population
    return PolicyOption(
        id=f"{event.id}-opt{branch_index + 1}-template",
        name=d["name"],
        description=d["description"],
        exposed_population_after=ground_exposed_after(baseline, d["factors"]),
        est_cost_usd=estimate_cost(baseline, branch_index),
        response_time_hours=d["response_time_hours"],
        tradeoffs=list(d["tradeoffs"]),
        affected_zones=default_zones(event, branch_index),
    )


def default_factors_for_branch(branch_index: int) -> list[str]:
    return list(_BRANCH_DEFAULTS[branch_index]["factors"])
