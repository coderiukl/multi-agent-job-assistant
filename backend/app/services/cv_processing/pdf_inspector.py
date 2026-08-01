from typing import Any

import fitz

from app.core.config import Settings
from app.core.exceptions import PDFInspectionException
from app.schemas.cv_processing import PageAnalysis
from app.services.cv_processing.page_classifier import (
    PageClassificationSignals,
    PageClassifier,
)


class PDFInspector:
    """Inspect PDF pages and produce page-level analysis."""

    def __init__(self, settings: Settings, classifier: PageClassifier) -> None:
        self.settings = settings
        self.classifier = classifier

    def inspect_bytes(self, content: bytes) -> list[PageAnalysis]:
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except fitz.FileDataError as exc:
            raise PDFInspectionException(message="PDF cannot be opened.") from exc

        try:
            if document.is_encrypted:
                raise PDFInspectionException(
                    message="Encrypted PDF is not supported.",
                )

            if document.page_count > self.settings.max_pdf_pages:
                raise PDFInspectionException(
                    message="PDF exceeds maximum page limit.",
                    details={
                        "page_count": document.page_count,
                        "max_pdf_pages": self.settings.max_pdf_pages,
                    },
                )

            analyses: list[PageAnalysis] = []

            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                analyses.append(
                    self._inspect_page(
                        page=page,
                        page_number=page_index + 1,
                    )
                )

            return analyses
        finally:
            document.close()

    def _inspect_page(self, page: fitz.Page, page_number: int) -> PageAnalysis:
        page_dict = page.get_text("dict")
        rect = page.rect
        page_area = max(float(rect.width * rect.height), 1.0)

        text = self._extract_text(page_dict)
        text_length = len(text.strip())
        text_block_count = self._count_blocks(page_dict, block_type=0)
        image_count = self._count_blocks(page_dict, block_type=1)

        text_coverage = self._calculate_coverage(
            page_dict,
            block_type=0,
            page_area=page_area,
        )
        image_coverage = self._calculate_coverage(
            page_dict,
            block_type=1,
            page_area=page_area,
        )

        has_encoding_issues = self._has_encoding_issues(text)

        signals = PageClassificationSignals(
            text_length=text_length,
            text_block_count=text_block_count,
            image_count=image_count,
            image_coverage=image_coverage,
            text_coverage=text_coverage,
            has_encoding_issues=has_encoding_issues,
        )

        page_type = self.classifier.classify(signals)

        return PageAnalysis(
            page_number=page_number,
            width=float(rect.width),
            height=float(rect.height),
            text_length=text_length,
            text_block_count=text_block_count,
            image_count=image_count,
            image_coverage=image_coverage,
            text_coverage=text_coverage,
            page_type=page_type,
            has_encoding_issues=has_encoding_issues,
        )

    def _extract_text(self, page_dict: dict[str, Any]) -> str:
        parts: list[str] = []

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text:
                        parts.append(text)

        return " ".join(parts)

    def _count_blocks(self, page_dict: dict[str, Any], *, block_type: int) -> int:
        return sum(
            1
            for block in page_dict.get("blocks", [])
            if block.get("type") == block_type
        )

    def _calculate_coverage(
        self,
        page_dict: dict[str, Any],
        *,
        block_type: int,
        page_area: float,
    ) -> float:
        total_area = 0.0

        for block in page_dict.get("blocks", []):
            if block.get("type") != block_type:
                continue

            bbox = block.get("bbox")
            if not bbox:
                continue

            total_area += self._bbox_area(bbox)

        return min(total_area / page_area, 1.0)

    def _bbox_area(self, bbox: list[float] | tuple[float, ...]) -> float:
        x0, y0, x1, y1 = bbox

        width = max(0.0, float(x1) - float(x0))
        height = max(0.0, float(y1) - float(y0))

        return width * height

    def _has_encoding_issues(self, text: str) -> bool:
        if not text:
            return False

        replacement_count = text.count("\ufffd")
        control_count = sum(
            1
            for char in text
            if ord(char) < 32 and char not in "\n\r\t"
        )

        suspicious_count = replacement_count + control_count
        return suspicious_count / max(len(text), 1) > 0.05