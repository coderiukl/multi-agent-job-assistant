from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class PaginationMeta(BaseModel):
    page: int = Field(ge=1, description="Current page number.")
    page_size: int = Field(ge=1, description="Number of items per page.")
    total: int = Field(ge=0, description="Total number of items.")
    total_pages: int = Field(ge=0, description="Total number of pages.")


class ApiResponse(BaseModel, Generic[DataT]):
    success: bool = Field(default=True, description="Request success status.")
    message: str = Field(
        default="Request completed successfully.",
        description="Response message.",
    )
    data: DataT | None = Field(default=None, description="Response payload.")
    meta: PaginationMeta | None = Field(
        default=None,
        description="Additional response metadata.",
    )