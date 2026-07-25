from app.utils.responses import paginated_response, success_response


def test_success_response() -> None:
    response = success_response(
        message="Done.",
        data={
            "status": "ok",
        },
    )

    assert response.success is True
    assert response.message == "Done."
    assert response.data == {
        "status": "ok",
    }
    assert response.meta is None


def test_paginated_response() -> None:
    response = paginated_response(
        message="Jobs retrieved successfully.",
        data=[
            {
                "id": "job_1",
            },
            {
                "id": "job_2",
            },
        ],
        page=2,
        page_size=2,
        total=5,
    )

    assert response.success is True
    assert response.message == "Jobs retrieved successfully."
    assert len(response.data) == 2
    assert response.meta is not None
    assert response.meta.page == 2
    assert response.meta.page_size == 2
    assert response.meta.total == 5
    assert response.meta.total_pages == 3