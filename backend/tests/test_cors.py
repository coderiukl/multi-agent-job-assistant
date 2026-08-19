from fastapi.testclient import TestClient

from app.main import app

ALLOWED_ORIGIN = "http://localhost:5173"


def test_cors_preflight_for_allowed_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "X-Request-ID" in response.headers


def test_cors_rejects_unknown_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
