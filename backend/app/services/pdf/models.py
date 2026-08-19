from dataclasses import dataclass


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