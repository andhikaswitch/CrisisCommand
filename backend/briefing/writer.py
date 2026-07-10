"""Fireworks AI situation-briefing writer (prompt P1).

One quality-critical call per event revision (ARCHITECTURE.md §5), validated
against backend.models.Briefing, with one P-R repair retry and a raw-data
fallback so the UI always has a briefing to show — even fully offline.

The no-invented-numbers spirit of the product applies here too: the fallback
brief states only facts already present in the event/population data.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from backend import cache
from backend.llm import prompts
from backend.llm.client import (
    ChatMessage,
    LLMBadJSON,
    LLMClient,
    LLMUnavailable,
    get_briefing_client,
    parse_json_object,
)
from backend.models import Briefing, CrisisEvent

logger = logging.getLogger(__name__)


def _event_json(event: CrisisEvent) -> str:
    payload = event.model_dump(mode="json")
    payload.pop("raw", None)  # never show raw feed payloads to the model
    return json.dumps(payload, ensure_ascii=False)


def _pop_json(event: CrisisEvent) -> str:
    if event.population_context is None:
        return "null"
    return json.dumps(event.population_context.model_dump(mode="json"), ensure_ascii=False)


def _fallback_brief(event: CrisisEvent) -> Briefing:
    """Raw-data brief: facts only, no assessment — the honest degraded path."""
    pop = event.population_context
    where = f"near {pop.nearest_city}, {event.country}" if pop else event.country
    exposed = f"~{pop.exposed_estimate:,} people in the exposure context" if pop else "unknown"
    return Briefing(
        headline=f"{event.kind.title()} reported in {event.country}",
        summary=(
            f"A {event.kind} event ({event.title}) is reported {where}, "
            f"beginning {event.started_at.strftime('%d %b %Y %H:%M UTC')}. "
            f"Normalized severity is "
            f"{event.severity:.2f} on a 0-1 scale from source {event.source}. "
            f"Population context: {exposed}. This is an automated fallback brief "
            "generated from feed data only because the briefing model was "
            "unavailable; it contains no analytical assessment."
        ),
        confirmed_facts=[
            f"Event type: {event.kind}",
            f"Location: {where} ({event.lat:.3f}, {event.lon:.3f})",
            f"Source: {event.source} ({event.source_url})",
            f"Normalized severity: {event.severity:.2f}",
        ],
        key_unknowns=[
            "On-the-ground impact not yet confirmed from this feed",
            "Local response status unknown",
        ],
        watch_indicators=[
            "Updated severity or magnitude from the source feed",
            "Secondary hazards (aftershocks, dam releases, storm surge)",
        ],
    )


async def _call_and_validate(
    client: LLMClient, messages: list[ChatMessage]
) -> Briefing:
    raw = await client.chat(messages, temperature=prompts.P1_TEMPERATURE)
    return Briefing.model_validate(parse_json_object(raw))


async def write_briefing(
    event: CrisisEvent,
    client: LLMClient | None = None,
    use_cache: bool = True,
) -> Briefing:
    """Produce a validated Briefing for an event.

    Path: cache -> P1 call -> P-R repair retry -> raw-data fallback.
    """
    key = ("brief", event.id, cache.event_revision(event))
    if use_cache:
        cached = cache.get(key, Briefing)
        if cached is not None:
            return cached

    client = client or get_briefing_client()
    messages = [
        ChatMessage("system", prompts.P1_SYSTEM),
        ChatMessage(
            "user",
            prompts.P1_USER.format(
                event_json=_event_json(event),
                population_context_json=_pop_json(event),
            ),
        ),
    ]

    briefing: Briefing | None = None
    try:
        briefing = await _call_and_validate(client, messages)
    except (LLMBadJSON, ValidationError) as exc:
        logger.warning("P1 invalid for %s, attempting repair: %s", event.id, exc)
        repair = messages + [
            ChatMessage(
                "user", prompts.PR_REPAIR.format(validation_error=str(exc))
            )
        ]
        try:
            briefing = await _call_and_validate(client, repair)
        except (LLMBadJSON, ValidationError, LLMUnavailable) as exc2:
            logger.warning("P1 repair failed for %s: %s", event.id, exc2)
    except LLMUnavailable as exc:
        logger.info("briefing backend unavailable for %s: %s", event.id, exc)

    if briefing is None:
        # Degraded output: never cache it. The on-disk cache survives restarts,
        # so persisting a fallback would keep serving "the briefing model was
        # unavailable" long after the key/endpoint is fixed. Retry next click.
        return _fallback_brief(event)

    if use_cache:
        cache.put(key, briefing)
    return briefing
