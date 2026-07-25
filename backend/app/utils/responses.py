from collections.abc import Sequence
from math import ceil
from typing import TypeVar

from app.schemas.response import ApiResponse, PaginationMeta

DataT = TypeVar("DataT")


def success_response(*, data: DataT | None = None, message: str = "Request completed successfully.") -> ApiResponse[DataT]:
    return ApiResponse(
        success=True,
        message=message,
        data=data,
    )


def paginated_response(*, data: Sequence[DataT], page: int, page_size: int, total: int, message: str = "Items retrieved successfully.") -> ApiResponse[Sequence[DataT]]:
    total_pages = ceil(total / page_size) if page_size > 0 else 0

    return ApiResponse(
        success=True,
        message=message,
        data=data,
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )