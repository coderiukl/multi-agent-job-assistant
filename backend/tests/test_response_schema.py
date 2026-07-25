from app.schemas.response import ApiResponse, PaginationMeta


def test_api_response_default_values() -> None:
    response = ApiResponse[dict[str, str]]()

    assert response.success is True
    assert response.message == "Request completed successfully."
    assert response.data is None
    assert response.meta is None


def test_api_response_with_data() -> None:
    response = ApiResponse(
        message="Created successfully.",
        data={
            "id": "cv_123",
        },
    )

    assert response.success is True
    assert response.message == "Created successfully."
    assert response.data == {
        "id": "cv_123",
    }


def test_pagination_meta() -> None:
    meta = PaginationMeta(
        page=1,
        page_size=20,
        total=45,
        total_pages=3,
    )

    assert meta.page == 1
    assert meta.page_size == 20
    assert meta.total == 45
    assert meta.total_pages == 3