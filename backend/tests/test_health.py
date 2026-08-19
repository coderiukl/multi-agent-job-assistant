from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data['status'] == "healthy"
    assert data["service"] == "Multi-Agent Job Assistant"
    assert data["version"] == "0.1.0"
    assert data["environment"] in {
        "development",
        "testing",
        "production",
    }

