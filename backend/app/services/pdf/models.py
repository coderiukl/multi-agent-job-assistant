from dataclasses import dataclass


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