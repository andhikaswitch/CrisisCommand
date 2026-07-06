"""LLM scenario-branch reasoning (vLLM on MI300X, Fireworks fallback).

Takes an event + Monte Carlo baseline and reasons over THREE policy branches
(aggressive / staged / monitor) — sent as ONE batch of concurrent requests to
the local vLLM endpoint, which is where MI300X batching shines
(ARCHITECTURE.md §4.2). Each branch:

  1. P2 call -> JSON
  2. validate + one P-R repair retry
  3. GROUND: recompute exposed_population_after from the vetted factors the
     option claims (impact_model), so no LLM-invented casualty number ever
     reaches the UI — the LLM narrates, the arithmetic is ours.
  4. on any failure, degrade to a fully-grounded template option.

The three branches never collapse into near-duplicates: the directive and
the template both enforce a spectrum.
"""

from __future__ import annotations

import asyncio
import json
import logging

from pydantic import BaseModel, ValidationError

from backend.llm import prompts
from backend.llm.client import (
    ChatMessage,
    LLMBadJSON,
    LLMClient,
    LLMUnavailable,
    get_scenario_client,
    parse_json_object,
)
from backend.models import CrisisEvent, GeoZone, HorizonForecast, PolicyOption
from backend.simulation import impact_model

logger = logging.getLogger(__name__)

# Factors the prompt is allowed to see/apply (PROMPTS.md note 2).
_MITIGATION_FACTORS_JSON = json.dumps(impact_model.MITIGATION_FACTORS)


class _LLMOption(BaseModel):
    """Loose schema for the raw P2 JSON before grounding."""

    name: str
    description: str
    applied_factors: list[str] = []
    exposed_population_after: tuple[int, int] | None = None
    est_cost_usd: tuple[int, int] | None = None
    response_time_hours: float | None = None
    tradeoffs: list[str] = []
    affected_zones: list[GeoZone] = []


def _event_json(event: CrisisEvent) -> str:
    payload = event.model_dump(mode="json")
    payload.pop("raw", None)
    return json.dumps(payload, ensure_ascii=False)


def _branch_messages(
    event: CrisisEvent,
    forecast: HorizonForecast,
    horizon: str,
    n_runs: int,
    branch_index: int,
) -> list[ChatMessage]:
    p10, p90 = forecast.exposed_population
    user = prompts.P2_USER.format(
        event_json=_event_json(event),
        n_runs=n_runs,
        horizon=horizon,
        exposed_p10=p10,
        exposed_p90=p90,
        severity_curve=json.dumps([round(s, 3) for s in forecast.severity_curve[::8]]),
        drivers=json.dumps(forecast.drivers),
        mitigation_factors_json=_MITIGATION_FACTORS_JSON,
        branch_directive=prompts.P2_BRANCH_DIRECTIVES[branch_index],
    )
    return [
        ChatMessage("system", prompts.P2_SYSTEM),
        ChatMessage("user", user),
    ]


def _ground(
    llm_opt: _LLMOption,
    event: CrisisEvent,
    forecast: HorizonForecast,
    branch_index: int,
) -> PolicyOption:
    """Turn a validated LLM option into a grounded PolicyOption.

    Keeps the LLM's narrative (name, description, tradeoffs, zones) but
    REPLACES exposed_population_after with server-side arithmetic on the
    vetted factors it applied. Falls back to the branch's default factors if
    the model named none valid, and to template zones/cost when missing.
    """
    baseline = forecast.exposed_population
    factors = [f for f in llm_opt.applied_factors if f in impact_model.MITIGATION_FACTORS]
    if not factors:
        factors = impact_model.default_factors_for_branch(branch_index)

    after = impact_model.ground_exposed_after(baseline, factors)

    cost = llm_opt.est_cost_usd
    if cost is None or cost[0] < 0 or cost[1] < cost[0]:
        cost = impact_model.estimate_cost(baseline, branch_index)

    rt = llm_opt.response_time_hours
    if rt is None or rt < 0:
        rt = impact_model._BRANCH_DEFAULTS[branch_index]["response_time_hours"]

    zones = _plausible_zones(llm_opt.affected_zones, event)
    if not zones:
        zones = impact_model.default_zones(event, branch_index)

    tradeoffs = llm_opt.tradeoffs or list(
        impact_model._BRANCH_DEFAULTS[branch_index]["tradeoffs"]
    )

    return PolicyOption(
        id=f"{event.id}-opt{branch_index + 1}",
        name=llm_opt.name.strip() or impact_model._BRANCH_DEFAULTS[branch_index]["name"],
        description=llm_opt.description.strip(),
        exposed_population_after=after,
        est_cost_usd=cost,
        response_time_hours=float(rt),
        tradeoffs=tradeoffs,
        affected_zones=zones,
    )


def _plausible_zones(zones: list[GeoZone], event: CrisisEvent) -> list[GeoZone]:
    """Drop zones the model placed implausibly far from the event (~>150km)."""
    kept: list[GeoZone] = []
    for z in zones:
        # crude degree box: ~1.5deg lat ~= 165km; be generous on lon
        if abs(z.lat - event.lat) <= 1.6 and abs(z.lon - event.lon) <= 2.2:
            kept.append(z)
    return kept


async def _run_branch(
    client: LLMClient,
    event: CrisisEvent,
    forecast: HorizonForecast,
    horizon: str,
    n_runs: int,
    branch_index: int,
) -> PolicyOption:
    messages = _branch_messages(event, forecast, horizon, n_runs, branch_index)
    try:
        raw = await client.chat(messages, temperature=prompts.P2_TEMPERATURE)
        opt = _LLMOption.model_validate(parse_json_object(raw))
        return _ground(opt, event, forecast, branch_index)
    except (LLMBadJSON, ValidationError) as exc:
        logger.warning(
            "P2 branch %d invalid for %s, repairing: %s", branch_index, event.id, exc
        )
        try:
            repair = messages + [
                ChatMessage("user", prompts.PR_REPAIR.format(validation_error=str(exc)))
            ]
            raw = await client.chat(repair, temperature=prompts.PR_TEMPERATURE)
            opt = _LLMOption.model_validate(parse_json_object(raw))
            return _ground(opt, event, forecast, branch_index)
        except (LLMBadJSON, ValidationError, LLMUnavailable) as exc2:
            logger.warning(
                "P2 branch %d repair failed for %s: %s", branch_index, event.id, exc2
            )
    except LLMUnavailable as exc:
        logger.info(
            "scenario backend unavailable (branch %d, %s): %s",
            branch_index, event.id, exc,
        )
    # Fallback: fully-grounded template option.
    return impact_model.build_template_option(event, forecast, branch_index)


async def generate_options(
    event: CrisisEvent,
    forecast: HorizonForecast,
    horizon: str,
    n_runs: int,
    client: LLMClient | None = None,
) -> list[PolicyOption]:
    """Generate exactly three grounded policy options, branches batched.

    The three P2 calls are dispatched concurrently (asyncio.gather) — against
    vLLM this is a single server-side batch; each branch degrades to a
    template on failure, so the result always has three valid options.
    """
    client = client or get_scenario_client()
    tasks = [
        _run_branch(client, event, forecast, horizon, n_runs, i) for i in range(3)
    ]
    return list(await asyncio.gather(*tasks))
