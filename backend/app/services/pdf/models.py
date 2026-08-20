from dataclasses import dataclass
from typing import Literal

TextExtractionMethod = Literal["native", "ocr"]

@dataclass(frozen=True, slots=True)
class PdfTextBlock:
    block_number: int
    bbox: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True, slots=True)
class PdfPageText:
    page_number: int
    text: str
    blocks: tuple[PdfTextBlock, ...]
    character_count: int
    word_count: int
    has_meaningful_text: bool


@dataclass(frozen=True, slots=True)
class NativeTextExtractionResult:
    pages: tuple[PdfPageText, ...]
    full_text: str
    total_character_count: int
    total_word_count: int
    native_page_count: int
    ocr_required_page_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PdfMetadata:
    title: str | None
    author: str | None
    subject: str | None
    keywords: str | None
    creator: str | None
    producer: str | None
    creation_date: str | None
    modification_date: str | None


@dataclass(frozen=True, slots=True)
class PdfInspectionResult:
    page_count: int
    is_repaired: bool
    metadata: PdfMetadata

@dataclass(frozen=True, slots=True)
class OcrTextLine:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class OcrPageText:
    page_number: int
    text: str
    lines: tuple[OcrTextLine, ...]
    character_count: int
    word_count: int
    average_confidence: float


@dataclass(frozen=True, slots=True)
class OcrTextExtractionResult:
    pages: tuple[OcrPageText, ...]
    full_text: str
    total_character_count: int
    total_word_count: int
    ocr_page_count: int

@dataclass(frozen=True, slots=True)
class UnifiedPdfPageText:
    page_number: int
    text: str
    method: TextExtractionMethod
    character_count: int
    word_count: int

@dataclass(frozen=True, slots=True)
class PdfTextMergeResult:
    pages: tuple[UnifiedPdfPageText, ...]
    full_text: str
    total_character_count: int
    total_word_count: int
    native_page_count: int
    ocr_page_count: int