from pydantic import BaseModel, Field


class PdfMetadataData(BaseModel):
    title: str | None
    author: str | None
    subject: str | None
    keywords: str | None
    creator: str | None
    producer: str | None
    creation_date: str | None
    modification_date: str | None


class PdfInspectionData(BaseModel):
    page_count: int = Field(ge=1)
    is_repaired: bool
    metadata: PdfMetadataData


class CVUploadData(BaseModel):
    file_id: str
    original_filename: str
    content_type: str
    size_bytes: int = Field(ge=1)
    inspection: PdfInspectionData