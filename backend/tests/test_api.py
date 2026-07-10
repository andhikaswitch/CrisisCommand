"""FastAPI skeleton tests: /api/events serves schema-valid seed data."""

from fastapi.testclient import TestClient

from backend.main import app
from backend.models import CrisisEvent

client = TestClient(app)


def test_list_events_returns_15_valid_events():
    r = client.get("/api/events")
    assert r.status_code == 200
    events = [CrisisEvent.model_validate(item) for item in r.json()]
    assert len(events) == 15


def test_get_single_event():
    r = client.get("/api/events/seed-FL-001")
    assert r.status_code == 200
    assert r.json()["kind"] == "flood"


def test_unknown_event_404s():
    assert client.get("/api/events/nope").status_code == 404


def test_gpu_health_readout():
    r = client.get("/api/health/gpu")
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] in ("gpu", "cpu")
    assert "device" in body


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


class TestSpaMount:
    """The SPA mount must never shadow the API (single-origin notebook demos)."""

    def test_api_routes_still_resolve_with_dist_present(self):
        from backend.main import _DIST, app

        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/health" in paths
        assert "/api/events" in paths
        assert "/ws" in paths
        if _DIST.is_dir():
            # mounted last, at root, so it only catches what the API didn't
            last = app.routes[-1]
            assert getattr(last, "name", None) == "spa"
