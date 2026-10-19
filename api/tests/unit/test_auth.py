from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.routers.health import database_check


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ALLOWED_EMAILS", "Hernan@Example.com, lauren@example.com")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[database_check] = lambda: lambda: True
    yield TestClient(app)
    get_settings.cache_clear()


def test_health_open_without_sign_in(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200


def test_rejects_anonymous_request(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 403


def test_rejects_unknown_account(client: TestClient) -> None:
    resp = client.get("/api/me", headers={"X-MS-CLIENT-PRINCIPAL-NAME": "someone@example.com"})
    assert resp.status_code == 403


@pytest.mark.parametrize("email", ["hernan@example.com", "LAUREN@example.com"])
def test_allows_household_accounts_case_insensitive(client: TestClient, email: str) -> None:
    resp = client.get("/api/me", headers={"X-MS-CLIENT-PRINCIPAL-NAME": email})
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
