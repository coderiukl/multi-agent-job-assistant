import re
import unicodedata

from app.services.pdf.models import (
    NativeTextExtractionResult,
    OcrTextExtractionResult,
    PdfTextMergeResult,
    TextExtractionMethod,
    UnifiedPdfPageText,
)

class PdfTextMerger:
    def merge(
        self,
        *,
        native_result: NativeTextExtractionResult,
        ocr_result: OcrTextExtractionResult,
    ) -> PdfTextMergeResult:

        ocr_pages = {
            page.page_number: page
            for page in ocr_result.pages
        }

        merged_pages: list[UnifiedPdfPageText] = []

        for native_page in native_result.pages:
            ocr_page = ocr_pages.get(
                native_page.page_number
            )

            text, method = self._select_page_text(
                native_text=native_page.text,
                has_meaningful_native_text=(
                    native_page.has_meaningful_text
                ),
                ocr_text= ocr_page.text if ocr_page is not None else ""           
            )

            normalized_text = self._normalize_text(text)

            merged_pages.append(
                UnifiedPdfPageText(
                    page_number=native_page.page_number,
                    text=normalized_text,
                    method=method,
                    character_count=self._count_characters(normalized_text),
                    word_count=len(normalized_text.split()),
                )
            )

        pages = tuple(merged_pages)

        full_text = "\n\n".join(page.text for page in pages if page.text)

        return PdfTextMergeResult(
            pages=pages,
            full_text=full_text,
            total_character_count=sum(page.character_count for page in pages),
            total_word_count=sum(page.word_count for page in pages),
            native_page_count=sum(page.method == "native" for page in pages),
            ocr_page_count=sum(page.method == "ocr" for page in pages),
        )

    @staticmethod
    def _select_page_text(
        *,
        native_text: str,
        has_meaningful_native_text: bool,
        ocr_text: str
    ) -> tuple[str, TextExtractionMethod]:
        if has_meaningful_native_text:
            return native_text, "native"

        if ocr_text.strip():
            return ocr_text, "ocr"

        return native_text, "native"

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)

        cleaned_lines: list[str] = []

        for line in normalized.splitlines():
            cleaned_line = re.sub(r"[ \t]+", " ", line).strip()

            if cleaned_line:
                cleaned_lines.append(cleaned_line)

        return "\n".join(cleaned_lines)

    @staticmethod
    def _count_characters(text: str) -> int:
        return sum(1 for character in text if not character.isspace())