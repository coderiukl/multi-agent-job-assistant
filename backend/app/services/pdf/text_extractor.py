import asyncio
import logging
import re
import unicodedata
from pathlib import Path

import pymupdf

from app.core.config import Settings
from app.core.exceptions import FileValidationException
from app.services.pdf.models import NativeTextExtractionResult, PdfPageText, PdfTextBlock

logger = logging.getLogger(__name__)

class NativePdfTextExtractor:
    def __init__(self, settings: Settings) -> None:
        self._min_chars_per_page = settings.min_native_text_chars_per_page

    async def extract(self, file_path: Path) -> NativeTextExtractionResult:
        return await asyncio.to_thread(self._extract_sync, file_path)

    def _extract_sync(self, file_path: Path) -> NativeTextExtractionResult:
        if not file_path.is_file():
            raise FileValidationException(
                message="PDF file does not exist.",
                details={"file_path": str(file_path)},
            )

        try:
            with pymupdf.open(str(file_path)) as document:
                if document.needs_pass:
                    raise FileValidationException(
                        message="Encrypted PDF cannot be extracted.",
                    )

                pages = tuple(
                    self._extract_page(
                        document.load_page(page_index),
                        page_number=page_index + 1,
                    )
                    for page_index in range(document.page_count)
                )

        except FileValidationException:
            raise
        except (pymupdf.EmptyFileError, pymupdf.FileDataError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Native PDF text extraction failed",
                extra={
                    "file_path": str(file_path),
                    "error_type": type(exc).__name__,
                },
            )
            raise FileValidationException(
                message="Unable to extract text from PDF.",
                details={"reason": type(exc).__name__},
            ) from exc
        except OSError as exc:
            logger.exception(
                "Unable to read PDF during text extraction",
                extra={"file_path": str(file_path)},
            )
            raise FileValidationException(
                message="Unable to read PDF file.",
            ) from exc

        total_character_count = sum(
            page.character_count for page in pages
        )

        total_word_count = sum(page.word_count for page in pages)

        ocr_required_pages = tuple(
            page.page_number
            for page in pages
            if not page.has_meaningful_text
        )

        full_text = "\n\n".join(page.text for page in pages if page.text)

        result = NativeTextExtractionResult(
            pages=pages,
            full_text=full_text,
            total_character_count=total_character_count,
            total_word_count=total_word_count,
            native_page_count=len(pages) - len(ocr_required_pages),
            ocr_required_page_numbers=ocr_required_pages,
        )

        logger.info(
            "Native PDF text extraction completed",
            extra={
                "file_path": str(file_path),
                "page_count": len(pages),
                "character_count": total_character_count,
                "word_count": total_word_count,
                "ocr_candidate_page_count": len(
                    ocr_required_pages
                ),
            },
        )

        return result

    def _extract_page(self, page: pymupdf.Page, page_number: int) -> PdfPageText:
        raw_blocks = page.get_text("blocks", sort=True)

        blocks: list[PdfTextBlock] = []

        for raw_block in raw_blocks:
            block_type = int(raw_block[0])

            # 0 là text block, 1 là image block
            if block_type != 0:
                continue

            text = self._normalize_text(str(raw_block[4]))

            if not text:
                continue

            blocks.append(
                PdfTextBlock(
                    block_number=int(raw_block[5]),
                    bbox=(
                        float(raw_block[0]),
                        float(raw_block[1]),
                        float(raw_block[2]),
                        float(raw_block[3]),
                    ),
                    text=text,
                )
            )

        page_text = "\n".join(block.text for block in blocks)

        character_count = sum(
            1 for character in page_text if not character.isspace()
        )

        word_count = len(page_text.split())

        return PdfPageText(
            page_number=page_number,
            text=page_text,
            blocks=tuple(blocks),
            character_count=character_count,
            word_count=word_count,
            has_meaningful_text=(
                character_count
                >= self._min_chars_per_page
            ),
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("\r\n", "\n")
        normalized = normalized.replace("\r", "\n")

        cleaned_lines = []

        for line in normalized.splitlines():
            cleaned_line = re.sub("r[ \t]+", " ", line).strip()

            if cleaned_line:
                cleaned_lines.append(cleaned_line)

        return "\n".join(cleaned_lines)
    
