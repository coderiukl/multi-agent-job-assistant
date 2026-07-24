from typing import Any

from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    field: str | None = Field(default=None, description="Tên field gây ra lỗi.")
    message: str = Field(description="Mô tả chi tiết lỗi.")
    type: str | None = Field(default=None, description="Loại lỗi.")

class ErrorResponse(BaseModel):
    code: str = Field(description="Mã lỗi dùng cho frontend hoặc client.", examples=["VALIDATION_ERROR"])
    message: str = Field(description="Thông báo lỗi tổng quát.")
    details: list[ErrorDetail] | dict[str, Any] | None = Field(default=None, description="Thông tin chi tiết của lỗi.")
