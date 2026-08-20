from pydantic import BaseModel, Field
from app.schemas.cv_profile import CVProfile


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

class NativeTextExtractionData(BaseModel):
    total_character_count: int = Field(ge=0)
    total_word_count: int = Field(ge=0)
    native_page_count: int = Field(ge=0)
    ocr_required_page_numbers: list[int]

class OcrExtractionData(BaseModel):
    ocr_page_count: int = Field(ge=0)
    total_character_count: int = Field(ge=0)
    total_word_count: int = Field(ge=0)
    average_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

class CVUploadData(BaseModel):
    file_id: str
    file_name: str
    file_size: int = Field(ge=1)
    content_type: str
    inspection: PdfInspectionData
    extraction: NativeTextExtractionData
    ocr: OcrExtractionData
    profile: CVProfile
