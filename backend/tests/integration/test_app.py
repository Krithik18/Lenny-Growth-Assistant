import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    settings = Settings(_env_file=None, database_url="", cors_origins=["http://localhost:5173"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_and_openapi(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready", "database": "not_configured"}
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/health/live" in schema.json()["paths"]
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize(
    "origin,expected_status",
    [("http://localhost:5173", 200), ("https://untrusted.example", 400)],
)
def test_cors_preflight(client, origin, expected_status):
    response = client.options(
        "/health/live",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers


def test_dotenv_settings_reach_api(tmp_path, monkeypatch):
    for name in ("APP_NAME", "APP_ENV", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        'APP_NAME="Configured test API"\n'
        'APP_ENV=test\n'
        'CORS_ORIGINS=["https://frontend.example"]\n'
        'FUTURE_SETTING=ignored\n',
        encoding="utf-8",
    )
    with TestClient(create_app(Settings(_env_file=env_file, database_url=""))) as client:
        assert client.get("/openapi.json").json()["info"]["title"] == "Configured test API"
        allowed = client.get("/health/live", headers={"Origin": "https://frontend.example"})
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://frontend.example"
        assert "access-control-allow-credentials" not in allowed.headers
        old_origin = client.get("/health/live", headers={"Origin": "http://localhost:5173"})
        assert "access-control-allow-origin" not in old_origin.headers


@pytest.mark.parametrize(
    "method,header", [("PUT", "Authorization"), ("GET", "X-Unapproved-Header")]
)
def test_disallowed_cors_method_or_header(client, method, header):
    response = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": header,
        },
    )
    assert response.status_code == 400
