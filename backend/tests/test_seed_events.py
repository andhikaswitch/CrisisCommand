"""Seed dataset integrity tests (ARCHITECTURE.md §3 seed mode)."""

from scripts.seed_events import load_seed_events


def test_exactly_15_events():
    assert len(load_seed_events()) == 15


def test_ids_unique_and_source_prefixed():
    events = load_seed_events()
    ids = [e.id for e in events]
    assert len(set(ids)) == len(ids)
    assert all(e.id.startswith("seed-") for e in events)


def test_kind_coverage_matches_plan():
    """Day 1 plan: floods, quakes, cyclone, wildfire + exactly 2 tension signals."""
    kinds = [e.kind for e in load_seed_events()]
    assert kinds.count("tension") == 2
    for required in ("flood", "earthquake", "cyclone", "wildfire"):
        assert kinds.count(required) >= 2, f"expected >=2 {required} events"
    assert "volcano" in kinds and "drought" in kinds


def test_all_have_population_context():
    for e in load_seed_events():
        assert e.population_context is not None, e.id
        assert e.population_context.exposed_estimate > 0, e.id


def test_severity_and_coords_in_bounds():
    for e in load_seed_events():
        assert 0.0 <= e.severity <= 1.0
        assert -90 <= e.lat <= 90 and -180 <= e.lon <= 180


def test_all_documented_with_source_urls():
    """Honesty rule: every seed event traces to a public, documented source."""
    for e in load_seed_events():
        assert e.source == "SEED"
        assert e.source_url.startswith("https://"), e.id


def test_timestamps_are_utc():
    for e in load_seed_events():
        assert e.started_at.utcoffset().total_seconds() == 0, e.id


def test_jakarta_flood_demo_star_present():
    """The demo script (CLAUDE.md) clicks the Jakarta flood — it must exist."""
    events = {e.id: e for e in load_seed_events()}
    jakarta = events["seed-FL-001"]
    assert jakarta.kind == "flood"
    assert jakarta.country == "Indonesia"
