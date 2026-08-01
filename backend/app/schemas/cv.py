from pydantic import BaseModel, Field

class CvUploadResponse(BaseModel):
    file_id: str = Field(description="Stored file indentifier.")
    filename: str = Field(description="Stored filename.")
    original_filename: str | None = Field(default=None, description="Original uploaded filename.")
    content_type: str | None = Field(default=None, description="Uploaded file content type.")
    size_bytes: int = Field(ge=0, description="Stored file size in bytes.")
    