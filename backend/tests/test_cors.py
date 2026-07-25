from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_preflight_allowed_origin() -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_disallowed_origin() -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://malicious.local",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400