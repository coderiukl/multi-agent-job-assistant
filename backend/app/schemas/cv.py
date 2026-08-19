from pydantic import BaseModel, Field


class CVUploadData(BaseModel):
    file_id: str
    original_filename: str
    content_type: str
    size_bytes: int = Field(ge=1)