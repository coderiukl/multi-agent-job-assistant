from fastapi.testclient import TestClient

from app.main import app
from app.middlewares.request_id import REQUEST_ID_HEADER

client = TestClient(app)


def test_request_id_is_added_to_response() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers


def test_existing_request_id_is_reused() -> None:
    request_id = "test-request-id"

    response = client.get(
        "/api/v1/health",
        headers={
            REQUEST_ID_HEADER: request_id,
        },
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == request_id