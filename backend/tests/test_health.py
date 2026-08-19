from fastapi.testclient import TestClient

from app.main import app


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers

    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Service is healthy."
    assert body["meta"] is None
    assert body["data"]["status"] == "healthy"
    assert body["data"]["service"] == "Multi-Agent Job Assistant"
    assert body["data"]["version"] == "0.1.0"
    assert body["data"]["environment"] in {
        "development",
        "testing",
        "production",
    }
