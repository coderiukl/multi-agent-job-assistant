from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class PaginationMeta(BaseModel):
    page: int = Field(ge=1, description="Current page number.")
    page_size: int = Field(
        ge=1,
        le=100,
        description="Number of items per page.",
    )
    total: int = Field(ge=0, description="Total number of items.")
    total_pages: int = Field(ge=0, description="Total number of pages.")


class ApiResponse(BaseModel, Generic[DataT]):
    success: Literal[True] = True
    message: str = Field(
        default="Request completed successfully.",
        description="Human-readable response message.",
    )
    data: DataT | None = Field(default=None, description="Response payload.")
    meta: PaginationMeta | None = Field(
        default=None,
        description="Pagination or additional response metadata.",
    )
