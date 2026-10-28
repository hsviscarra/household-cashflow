from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.routers.health import database_check


def _client(db_ok: bool) -> TestClient:
    app = create_app()

    def fake_check() -> Callable[[], bool]:
        return lambda: db_ok

    app.dependency_overrides[database_check] = fake_check
    return TestClient(app)


def test_health_ok_when_database_answers() -> None:
    resp = _client(db_ok=True).get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"]


def test_health_degraded_when_database_down() -> None:
    resp = _client(db_ok=False).get("/api/health")
    assert resp.status_code == 503
    assert resp.json()["database"] == "unavailable"


def test_real_check_reports_false_without_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    from app.db import get_engine

    get_engine.cache_clear()
    assert database_check()() is False
    get_settings.cache_clear()


def test_me_reads_easy_auth_header() -> None:
    client = _client(db_ok=True)
    assert client.get("/api/me").json() == {"name": None, "authenticated": False}
    resp = client.get("/api/me", headers={"X-MS-CLIENT-PRINCIPAL-NAME": "hernan@example.com"})
    assert resp.json() == {"name": "hernan@example.com", "authenticated": True}


def test_serves_web_build_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<html>cash flow</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    monkeypatch.setenv("WEB_DIST_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        resp = client.get("/")
        assert resp.status_code == 200
        assert "cash flow" in resp.text
        # A new release shows on the next visit: the page is always rechecked; hashed assets
        # are kept.
        assert resp.headers["cache-control"] == "no-cache"
        asset = client.get("/assets/index-abc123.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        deep_link = client.get("/import")
        assert deep_link.status_code == 200
        assert "cash flow" in deep_link.text
        assert deep_link.headers["cache-control"] == "no-cache"
        assert client.get("/api/unknown").status_code == 404
    finally:
        get_settings.cache_clear()
