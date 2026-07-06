"""Scenario agent: grounding (no invented numbers), fallback, spectrum.

The grounding test is the ethical core of the product (PROMPTS.md note 1):
whatever number the LLM emits for exposed_population_after, the value that
reaches the UI must be pure arithmetic on the Monte Carlo baseline and the
vetted mitigation factors.
"""

import asyncio
import json

from backend.llm.client import LLMUnavailable
from backend.models import HorizonForecast, PolicyOption
from backend.simulation import impact_model, scenario_agent
from backend.tests.conftest import FakeLLM
from scripts.seed_events import load_seed_events

EVENTS = {e.id: e for e in load_seed_events()}
JAKARTA = EVENTS["seed-FL-001"]


def _forecast(p10=1000, p90=5000) -> HorizonForecast:
    return HorizonForecast(
        exposed_population=(p10, p90),
        severity_curve=[0.2, 0.4, 0.6, 0.5],
        confidence="medium",
        drivers=["rainfall intensity", "drainage capacity"],
    )


def _good_branch_json(invented_after) -> str:
    return json.dumps(
        {
            "name": "Immediate staged evacuation",
            "description": "Evacuate the highest-exposure zones now and open shelters.",
            "applied_factors": ["timely_staged_evacuation"],
            "exposed_population_after": invented_after,
            "est_cost_usd": [2_000_000, 9_000_000],
            "response_time_hours": 5.0,
            "tradeoffs": ["high cost", "compliance risk", "political fallout"],
            "affected_zones": [
                {"shape": "circle", "lat": JAKARTA.lat, "lon": JAKARTA.lon,
                 "radius_km": 25.0, "role": "evacuation"}
            ],
        }
    )


class TestGrounding:
    def test_invented_number_is_overridden_by_arithmetic(self):
        """LLM claims an absurd after-range; server must recompute it."""
        forecast = _forecast(1000, 5000)
        # LLM tries to invent "2 people exposed" — must NOT survive.
        fake = FakeLLM(responses=[_good_branch_json([1, 2])] * 3)
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, forecast, "24h", 10000, client=fake)
        )
        expected = impact_model.ground_exposed_after(
            (1000, 5000), ["timely_staged_evacuation"]
        )
        assert opts[0].exposed_population_after == expected
        assert opts[0].exposed_population_after != (1, 2)

    def test_narrative_from_llm_is_kept(self):
        fake = FakeLLM(responses=[_good_branch_json([250, 2250])] * 3)
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, _forecast(), "24h", 10000, client=fake)
        )
        assert "Evacuate" in opts[0].description
        assert opts[0].name == "Immediate staged evacuation"

    def test_missing_factors_fall_back_to_branch_defaults(self):
        bad = json.dumps({
            "name": "Vague plan", "description": "do things",
            "applied_factors": ["not_a_real_factor"],
            "tradeoffs": ["x"], "affected_zones": [],
        })
        fake = FakeLLM(responses=[bad] * 3)
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, _forecast(1000, 5000), "24h", 10000, client=fake)
        )
        # Grounded with branch-0 default factors, not left ungrounded.
        expected = impact_model.ground_exposed_after(
            (1000, 5000), impact_model.default_factors_for_branch(0)
        )
        assert opts[0].exposed_population_after == expected


class TestRepairAndFallback:
    def test_bad_json_then_repair_succeeds(self):
        fake = FakeLLM(responses=[
            "not json at all",              # branch 0 first attempt
            _good_branch_json([250, 2250]),  # branch 0 repair
            _good_branch_json([250, 2250]),  # branch 1
            _good_branch_json([250, 2250]),  # branch 2
        ])
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, _forecast(), "24h", 10000, client=fake)
        )
        assert len(opts) == 3
        assert all(isinstance(o, PolicyOption) for o in opts)

    def test_backend_unavailable_uses_templates(self):
        fake = FakeLLM(raise_exc=LLMUnavailable("droplet down"))
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, _forecast(), "24h", 10000, client=fake)
        )
        assert len(opts) == 3
        assert all(o.id.endswith("-template") for o in opts)


class TestSpectrum:
    def test_always_three_distinct_options(self):
        fake = FakeLLM(raise_exc=LLMUnavailable("offline"))
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, _forecast(), "24h", 10000, client=fake)
        )
        assert len({o.name for o in opts}) == 3


class TestImplausibleZonesDropped:
    def test_far_away_zone_removed(self):
        far = json.dumps({
            "name": "Immediate staged evacuation",
            "description": "Evacuate now.",
            "applied_factors": ["timely_staged_evacuation"],
            "exposed_population_after": [250, 2250],
            "est_cost_usd": [1_000_000, 5_000_000],
            "response_time_hours": 5.0,
            "tradeoffs": ["cost", "politics"],
            "affected_zones": [
                {"shape": "circle", "lat": JAKARTA.lat + 40, "lon": JAKARTA.lon + 40,
                 "radius_km": 25.0, "role": "evacuation"}
            ],
        })
        fake = FakeLLM(responses=[far] * 3)
        opts = asyncio.run(
            scenario_agent.generate_options(JAKARTA, _forecast(), "24h", 10000, client=fake)
        )
        # Implausible zone dropped -> replaced by template default zones near event.
        for z in opts[0].affected_zones:
            assert abs(z.lat - JAKARTA.lat) <= 1.6
