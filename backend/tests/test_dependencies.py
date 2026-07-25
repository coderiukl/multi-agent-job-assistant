from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps.common import get_request_id


def test_get_request_id_from_request_state() -> None:
    app = FastAPI()

    @app.get("/request-id")
    async def read_request_id(request_id: str | None = None) -> dict[str, str | None]:
        return {
            "request_id": request_id,
        }

    app.dependency_overrides[get_request_id] = lambda: "test-request-id"

    client = TestClient(app)
    response = client.get("/request-id")

    assert response.status_code == 200