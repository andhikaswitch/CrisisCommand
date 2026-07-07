"""Day 5 ingestion: normalizer, USGS/GDACS parsing, GPU embed/dedup, store."""

import torch
from fastapi.testclient import TestClient

from backend.ingest import (
    bmkg,
    embeddings,
    gdacs,
    news,
    normalizer,
    reliefweb,
    usgs,
)
from backend.ingest.store import EventStore
from backend.main import app

client = TestClient(app)


# --- fixtures shaped like the real public payloads ------------------------

USGS_PAYLOAD = {
    "features": [
        {
            "id": "us7000abcd",
            "properties": {
                "mag": 6.4, "place": "20 km S of Town, Chile",
                "time": 1_700_000_000_000, "url": "https://earthquake.usgs.gov/x",
                "title": "M 6.4 - 20 km S of Town, Chile",
            },
            "geometry": {"coordinates": [-71.5, -33.2, 30.0]},
        },
        {  # malformed: no magnitude — must be skipped, not crash
            "id": "bad", "properties": {"place": "nowhere", "time": 1_700_000_000_000},
            "geometry": {"coordinates": [0, 0, 0]},
        },
    ]
}

GDACS_PAYLOAD = {
    "features": [
        {
            "properties": {
                "eventtype": "FL", "alertlevel": "Orange", "country": "Bangladesh",
                "name": "Flood in Bangladesh", "eventid": 12345,
                "fromdate": "2024-07-01T00:00:00", "alertscore": 1.8,
                "url": {"report": "https://www.gdacs.org/report/FL/12345"},
            },
            "geometry": {"coordinates": [90.4, 23.7]},
        },
        {  # event type we don't model — dropped
            "properties": {
                "eventtype": "TS", "alertlevel": "Green", "country": "X",
                "eventid": 1, "fromdate": "2024-07-01T00:00:00",
            },
            "geometry": {"coordinates": [0, 0]},
        },
    ]
}


class TestNormalizer:
    def test_usgs_severity_monotonic(self):
        assert normalizer.normalize_severity_usgs(4.0) < normalizer.normalize_severity_usgs(7.0)
        assert normalizer.normalize_severity_usgs(9.5) == 1.0

    def test_gdacs_alert_mapping(self):
        red = normalizer.normalize_severity_gdacs("Red")
        green = normalizer.normalize_severity_gdacs("Green")
        assert red > green

    def test_gdacs_kind_mapping(self):
        assert normalizer.gdacs_kind("EQ") == "earthquake"
        assert normalizer.gdacs_kind("FL") == "flood"
        assert normalizer.gdacs_kind("XX") is None

    def test_iso_parse_utc(self):
        dt = normalizer.parse_iso_utc("2024-07-01T00:00:00Z")
        assert dt.utcoffset().total_seconds() == 0


class TestUsgsParse:
    def test_maps_and_skips_malformed(self):
        events = usgs.parse_feed(USGS_PAYLOAD)
        assert len(events) == 1
        e = events[0]
        assert e.kind == "earthquake"
        assert e.id == "usgs-us7000abcd"
        assert e.country == "Chile"
        assert e.source == "USGS"
        assert e.population_context is None  # live events carry no exposure base

    def test_empty_payload(self):
        assert usgs.parse_feed({}) == []


class TestGdacsParse:
    def test_maps_and_drops_unmodeled(self):
        events = gdacs.parse_feed(GDACS_PAYLOAD)
        assert len(events) == 1
        e = events[0]
        assert e.kind == "flood"
        assert e.country == "Bangladesh"
        assert e.source_url == "https://www.gdacs.org/report/FL/12345"
        assert e.id.startswith("gdacs-FL-")

    def test_short_or_missing_coordinates_skipped(self):
        # regression: a live GDACS feature had a <2-element coordinates list
        payload = {"features": [
            {"properties": {"eventtype": "FL", "alertlevel": "Red", "eventid": 9,
                            "fromdate": "2024-07-01T00:00:00"},
             "geometry": {"coordinates": [12.3]}},
            {"properties": {"eventtype": "EQ", "alertlevel": "Red", "eventid": 8,
                            "fromdate": "2024-07-01T00:00:00"},
             "geometry": {}},
        ]}
        assert gdacs.parse_feed(payload) == []


BMKG_PAYLOAD = {
    "Infogempa": {
        "gempa": [
            {
                "DateTime": "2026-07-07T07:16:27+00:00",
                "Coordinates": "3.14,127.44",
                "Magnitude": "5.6",
                "Kedalaman": "10 km",
                "Wilayah": "101 km BaratLaut PULAUDOI-MALUT",
                "Potensi": "Tidak berpotensi tsunami",
            },
            {  # tsunami-potential quake gets a severity floor
                "DateTime": "2026-07-06T08:41:35+00:00",
                "Coordinates": "-9.5,119.0",
                "Magnitude": "7.1",
                "Wilayah": "SUMBA",
                "Potensi": "Berpotensi tsunami",
            },
            {"Coordinates": "broken", "Magnitude": "x"},  # malformed — skipped
        ]
    }
}


class TestBmkgParse:
    def test_maps_and_skips_malformed(self):
        events = bmkg.parse_feed(BMKG_PAYLOAD)
        assert len(events) == 2
        e = events[0]
        assert e.kind == "earthquake"
        assert e.source == "BMKG"
        assert e.country == "Indonesia"
        assert (e.lat, e.lon) == (3.14, 127.44)
        assert e.started_at.utcoffset().total_seconds() == 0
        assert e.population_context is None

    def test_tsunami_potential_floors_severity(self):
        events = bmkg.parse_feed(BMKG_PAYLOAD)
        assert events[1].severity >= 0.75

    def test_empty_payload(self):
        assert bmkg.parse_feed({}) == []


class TestNewsTension:
    PAYLOAD = {"articles": [
        {"title": f"Conflict headline number {i}", "seendate": "20260707T100000Z"}
        for i in range(40)
    ]}

    def test_article_stats(self):
        count, samples = news.article_stats(self.PAYLOAD)
        assert count == 40
        assert len(samples) == 3

    def test_severity_capped_below_red(self):
        assert news.severity_from_count(75) <= news.SEVERITY_CAP
        assert news.severity_from_count(200) <= news.SEVERITY_CAP
        assert news.severity_from_count(15) < news.severity_from_count(75)

    def test_build_event_is_low_confidence_tension(self):
        fp = news.WATCHLIST[0]
        count, samples = news.article_stats(self.PAYLOAD)
        e = news.build_event(fp, count, samples)
        assert e.kind == "tension"
        assert e.source == "GDELT"
        assert e.severity <= news.SEVERITY_CAP
        assert e.raw["signal"] == "news-cluster"
        assert len(e.raw["sample_headlines"]) == 3
        assert e.population_context is None  # never simulable

    def test_quiet_region_below_threshold(self):
        assert 5 < news.EMIT_THRESHOLD  # 5 articles must NOT emit
        # fetch() gates on EMIT_THRESHOLD; severity fn itself stays defined


class TestReliefWeb:
    PAYLOAD = {"data": [
        {
            "id": 52001,
            "fields": {
                "name": "Mozambique: Tropical Cyclone Alpha - Jan 2026",
                "status": "ongoing",
                "url": "https://reliefweb.int/taxonomy/term/52001",
                "date": {"created": "2026-01-10T00:00:00+00:00"},
                "type": [{"name": "Tropical Cyclone"}],
                "primary_country": {
                    "name": "Mozambique",
                    "location": {"lat": -18.66, "lon": 35.53},
                },
            },
        },
        {  # unmapped type — dropped
            "id": 52002,
            "fields": {
                "name": "X: Epidemic", "status": "ongoing",
                "date": {"created": "2026-01-10T00:00:00+00:00"},
                "type": [{"name": "Epidemic"}],
                "primary_country": {"name": "X", "location": {"lat": 0, "lon": 0}},
            },
        },
        {  # past status — dropped
            "id": 52003,
            "fields": {
                "name": "Y: Flood", "status": "past",
                "date": {"created": "2026-01-10T00:00:00+00:00"},
                "type": [{"name": "Flood"}],
                "primary_country": {"name": "Y", "location": {"lat": 1, "lon": 1}},
            },
        },
    ]}

    def test_maps_and_filters(self):
        events = reliefweb.parse_feed(self.PAYLOAD)
        assert len(events) == 1
        e = events[0]
        assert e.kind == "cyclone"
        assert e.id == "reliefweb-52001"
        assert e.country == "Mozambique"
        assert e.severity == 0.55  # ongoing

    def test_disabled_without_appname(self, monkeypatch):
        monkeypatch.delenv("RELIEFWEB_APPNAME", raising=False)
        assert not reliefweb.enabled()


class TestFloodRisk:
    def _payload(self, tps, start_hours=1):
        """Forecast payload with 3h-spaced entries carrying the given tp values."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        entries = [
            {
                "datetime": (now + timedelta(hours=start_hours + 3 * i))
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tp": tp,
            }
            for i, tp in enumerate(tps)
        ]
        return {"data": [{"cuaca": [entries]}]}

    def test_heavy_rain_over_prone_region_emits_signal(self):
        from backend.ingest import flood_risk

        payload = self._payload([25, 30, 28, 20])  # 103mm in 24h
        total, peak = flood_risk.rain_totals(payload)
        assert total > 100 and peak == 30
        region = flood_risk.FLOOD_PRONE_REGIONS[0]  # Bogor, propensity 0.85
        risk = flood_risk.risk_score(total, peak, region.propensity)
        assert risk >= flood_risk.RISK_THRESHOLD
        e = flood_risk.build_event(region, total, peak, risk)
        assert e.kind == "flood"
        assert e.source == "BMKG-RAIN"
        assert "forecast" in e.title.lower()
        assert e.severity <= flood_risk.SEVERITY_CAP  # signal, never red event
        assert e.raw["signal"] == "forecast"

    def test_dry_forecast_emits_nothing(self):
        from backend.ingest import flood_risk

        total, peak = flood_risk.rain_totals(self._payload([0, 0, 1, 0]))
        risk = flood_risk.risk_score(total, peak, 0.9)
        assert risk < flood_risk.RISK_THRESHOLD

    def test_rain_outside_24h_window_ignored(self):
        from backend.ingest import flood_risk

        payload = self._payload([50, 50], start_hours=30)  # beyond horizon
        total, peak = flood_risk.rain_totals(payload)
        assert total == 0 and peak == 0

    def test_risk_scales_with_propensity(self):
        from backend.ingest import flood_risk

        low = flood_risk.risk_score(60, 20, 0.3)
        high = flood_risk.risk_score(60, 20, 0.9)
        assert high > low

    def test_openmeteo_parsing_and_global_event(self):
        from datetime import datetime, timedelta, timezone

        from backend.ingest import flood_risk

        now = datetime.now(timezone.utc)
        times = [(now + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M")
                 for h in range(30)]
        precip = [8.0] * 12 + [0.0] * 18  # 96mm in the first 12h
        result = {"hourly": {"time": times, "precipitation": precip}}
        total, peak = flood_risk.rain_totals_openmeteo(result)
        # first hourly entry may fall a few seconds before "now" (strftime
        # drops seconds) and be excluded — 11 or 12 of the 8mm hours count
        assert 85 <= total <= 100
        assert peak == 24.0  # 3h rolling burst
        dhaka = flood_risk.GLOBAL_FLOOD_PRONE[0]
        risk = flood_risk.risk_score(total, peak, dhaka.propensity)
        assert risk >= flood_risk.RISK_THRESHOLD
        e = flood_risk.build_event(dhaka, total, peak, risk,
                                   source=flood_risk.SOURCE_GLOBAL,
                                   source_url="https://open-meteo.com/")
        assert e.source == "OPEN-METEO"
        assert e.country == "Bangladesh"


class TestEmbeddings:
    def test_hash_deterministic(self):
        assert embeddings.hash_trigram("abc") == embeddings.hash_trigram("abc")

    def test_embed_shape_and_norm(self):
        vecs = embeddings.embed(["flood in jakarta", "earthquake in nepal"], torch.device("cpu"))
        assert vecs.shape == (2, embeddings.EMBED_DIM)
        norms = vecs.norm(dim=1)
        assert torch.allclose(norms, torch.ones(2), atol=1e-5)

    def test_similar_text_high_cosine(self):
        v = embeddings.embed(
            ["flood in jakarta indonesia", "flood in jakarta indonesia"],
            torch.device("cpu"),
        )
        sim = embeddings.cosine_matrix(v[:1], v[1:])[0, 0].item()
        assert sim > 0.99

    def test_different_text_low_cosine(self):
        v = embeddings.embed(
            ["earthquake nepal kathmandu", "cyclone mozambique beira"],
            torch.device("cpu"),
        )
        sim = embeddings.cosine_matrix(v[:1], v[1:])[0, 0].item()
        assert sim < embeddings.SIM_THRESHOLD

    def test_haversine_known_distance(self):
        # Jakarta -> Bandung is ~120 km
        d = embeddings.haversine_km(-6.21, 106.85, -6.91, 107.61)
        assert 100 < d < 160


class TestStoreDedup:
    def _event(self, id, lat, lon, sev=0.6, title="M6.5 earthquake near Testville"):
        return normalizer.make_event(
            id=id, kind="earthquake", title=title, lat=lat, lon=lon,
            country="Testland", severity=sev, started_at=normalizer.parse_iso_utc("2024-07-01T00:00:00Z"),
            source="USGS", source_url="https://example.org", raw={},
        )

    def test_duplicate_same_place_merges(self):
        store = EventStore(seed=False, force_cpu=True)
        r1 = store.add_from_source("USGS", [self._event("a", -6.2, 106.8)])
        r2 = store.add_from_source("GDACS", [self._event("b", -6.25, 106.82)])
        assert r1.added == 1
        assert r2.merged == 1 and r2.added == 0
        assert len(store.snapshot()) == 1

    def test_same_title_far_apart_not_merged(self):
        store = EventStore(seed=False, force_cpu=True)
        store.add_from_source("USGS", [self._event("a", -6.2, 106.8)])
        r = store.add_from_source("USGS", [self._event("b", 35.0, 139.0)])  # Tokyo
        assert r.added == 1
        assert len(store.snapshot()) == 2

    def test_merge_bumps_severity(self):
        store = EventStore(seed=False, force_cpu=True)
        store.add_from_source("USGS", [self._event("a", -6.2, 106.8, sev=0.5)])
        store.add_from_source("GDACS", [self._event("b", -6.2, 106.8, sev=0.9)])
        assert store.snapshot()[0].severity == 0.9

    def test_error_sets_source_status(self):
        store = EventStore(seed=False, force_cpu=True)
        store.add_from_source("GDACS", [], error="feed 503")
        health = {h.source: h for h in store.source_health()}["GDACS"]
        assert health.status() == "error"
        assert health.last_error == "feed 503"


class TestSeedStore:
    def test_seed_store_has_15_and_source_health(self):
        store = EventStore(seed=True, force_cpu=True)
        assert len(store.snapshot()) == 15
        assert store.get("seed-FL-001") is not None
        health = {h.source: h for h in store.source_health()}
        assert health["SEED"].status() == "ok"


class TestStatusEndpoint:
    def test_status_reports_mode_and_sources(self):
        r = client.get("/api/status")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "SEED"
        assert "sim_backend_degraded" in body
        assert any(s["source"] == "SEED" for s in body["sources"])
