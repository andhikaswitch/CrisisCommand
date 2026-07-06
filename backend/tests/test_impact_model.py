"""Impact model: factor arithmetic, grounding bounds, template options."""

from backend.models import HorizonForecast
from backend.simulation import impact_model
from scripts.seed_events import load_seed_events

EVENTS = {e.id: e for e in load_seed_events()}
JAKARTA = EVENTS["seed-FL-001"]


def _forecast(p10=1000, p90=5000) -> HorizonForecast:
    return HorizonForecast(
        exposed_population=(p10, p90),
        severity_curve=[0.2, 0.4, 0.6],
        confidence="medium",
        drivers=["rainfall"],
    )


class TestComposeFactors:
    def test_single_factor(self):
        assert impact_model.compose_factors(["timely_staged_evacuation"]) == (0.25, 0.45)

    def test_multiplicative_composition(self):
        low, high = impact_model.compose_factors(
            ["timely_staged_evacuation", "early_warning_broadcast"]
        )
        assert low == 0.25 * 0.70
        assert high == 0.45 * 0.90

    def test_unknown_keys_ignored(self):
        assert impact_model.compose_factors(["made_up_factor"]) == (1.0, 1.0)

    def test_empty_is_identity(self):
        assert impact_model.compose_factors([]) == (1.0, 1.0)


class TestGroundExposedAfter:
    def test_arithmetic_on_baseline(self):
        after = impact_model.ground_exposed_after((1000, 5000), ["timely_staged_evacuation"])
        assert after == (250, 2250)

    def test_never_exceeds_baseline(self):
        after = impact_model.ground_exposed_after((1000, 5000), ["enhanced_monitoring"])
        p10, p90 = after
        assert p10 <= 1000 and p90 <= 5000

    def test_ordering_preserved(self):
        p10, p90 = impact_model.ground_exposed_after((800, 9000), ["prepositioned_supplies"])
        assert 0 <= p10 <= p90


class TestEstimateCost:
    def test_monitoring_is_fixed_floor(self):
        assert impact_model.estimate_cost((1000, 5000), 2) == impact_model._MONITORING_FIXED_COST_USD

    def test_evacuation_scales_with_population(self):
        lo, hi = impact_model.estimate_cost((1000, 5000), 0)
        assert hi > lo > 0


class TestTemplateOptions:
    def test_all_three_valid_and_distinct(self):
        forecast = _forecast()
        opts = [
            impact_model.build_template_option(JAKARTA, forecast, i) for i in range(3)
        ]
        names = {o.name for o in opts}
        assert len(names) == 3
        for o in opts:
            assert o.affected_zones
            assert o.tradeoffs

    def test_spectrum_aggressive_reduces_most(self):
        forecast = _forecast()
        aggressive = impact_model.build_template_option(JAKARTA, forecast, 0)
        monitor = impact_model.build_template_option(JAKARTA, forecast, 2)
        # Aggressive evacuation must leave fewer exposed than monitoring.
        assert aggressive.exposed_population_after[1] < monitor.exposed_population_after[1]

    def test_political_tradeoff_present(self):
        opt = impact_model.build_template_option(JAKARTA, _forecast(), 0)
        assert len(opt.tradeoffs) >= 2
