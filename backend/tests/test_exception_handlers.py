from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppException


@pytest.fixture
def test_app() -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)

    @application.get("/application-error")
    async def raise_application_error() -> None:
        raise AppException(
            status_code=400,
            code="TEST_ERROR",
            message="Đây là lỗi test.",
            details={
                "reason": "testing",
            },
        )

    @application.get("/http-error")
    async def raise_http_error() -> None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy dữ liệu.",
        )

    @application.get("/validation-error")
    async def raise_validation_error(
        score: int = Query(ge=0, le=100),
    ) -> dict[str, int]:
        return {
            "score": score,
        }

    @application.get("/internal-error")
    async def raise_internal_error() -> None:
        raise RuntimeError("Sensitive internal error")

    return application


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(
        test_app,
        raise_server_exceptions=False,
    )


def test_app_exception_handler(client: TestClient) -> None:
    response = client.get("/application-error")

    assert response.status_code == 400
    assert response.json() == {
        "code": "TEST_ERROR",
        "message": "Đây là lỗi test.",
        "details": {
            "reason": "testing",
        },
    }


def test_http_exception_handler(client: TestClient) -> None:
    response = client.get("/http-error")

    assert response.status_code == 404
    assert response.json() == {
        "code": "HTTP_404",
        "message": "Không tìm thấy dữ liệu.",
    }


def test_validation_exception_handler(client: TestClient) -> None:
    response = client.get(
        "/validation-error",
        params={
            "score": 101,
        },
    )

    response_body: dict[str, Any] = response.json()

    assert response.status_code == 422
    assert response_body["code"] == "VALIDATION_ERROR"
    assert response_body["message"] == "Dữ liệu request không hợp lệ."
    assert isinstance(response_body["details"], list)
    assert response_body["details"][0]["field"] == "score"


def test_unhandled_exception_handler_does_not_expose_error(
    client: TestClient,
) -> None:
    response = client.get("/internal-error")

    response_body = response.json()

    assert response.status_code == 500
    assert response_body == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Hệ thống đã xảy ra lỗi. Vui lòng thử lại sau.",
    }

    assert "Sensitive internal error" not in response.text