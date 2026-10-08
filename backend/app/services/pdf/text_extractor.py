import asyncio
import logging
import re
import unicodedata
from pathlib import Path

import pymupdf

from app.core.config import Settings
from app.core.exceptions import FileValidationException
from app.services.pdf.models import (
    NativeTextExtractionResult,
    PdfPageText,
    PdfTextBlock,
)

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
        except (
            pymupdf.EmptyFileError,
            pymupdf.FileDataError,
            RuntimeError,
            ValueError,
        ) as exc:
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

        total_character_count = sum(page.character_count for page in pages)

        total_word_count = sum(page.word_count for page in pages)

        ocr_required_pages = tuple(
            page.page_number for page in pages if not page.has_meaningful_text
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
                "ocr_candidate_page_count": len(ocr_required_pages),
            },
        )

        return result

    def _extract_page(self, page: pymupdf.Page, page_number: int) -> PdfPageText:
        raw_blocks = page.get_text("blocks", sort=False)

        blocks: list[PdfTextBlock] = []

        for raw_block in raw_blocks:
            block_type = int(raw_block[6])

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

        blocks = self._order_blocks(blocks, page_width=float(page.rect.width))
        page_text = "\n".join(block.text for block in blocks)

        character_count = sum(1 for character in page_text if not character.isspace())

        word_count = len(page_text.split())
        quality_score, quality_issues = self._assess_quality(
            page=page,
            blocks=blocks,
            text=page_text,
            character_count=character_count,
            word_count=word_count,
        )

        return PdfPageText(
            page_number=page_number,
            text=page_text,
            blocks=tuple(blocks),
            character_count=character_count,
            word_count=word_count,
            has_meaningful_text=quality_score >= 0.65,
            quality_score=quality_score,
            quality_issues=quality_issues,
        )

    @staticmethod
    def _order_blocks(
        blocks: list[PdfTextBlock],
        *,
        page_width: float,
    ) -> list[PdfTextBlock]:
        """Use column-major order when a page has two distinct text columns."""
        if len(blocks) < 4 or page_width <= 0:
            return sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))

        spanning = [
            block
            for block in blocks
            if (block.bbox[2] - block.bbox[0]) >= page_width * 0.65
        ]
        narrow = [block for block in blocks if block not in spanning]
        left = [
            block
            for block in narrow
            if ((block.bbox[0] + block.bbox[2]) / 2) < page_width * 0.48
        ]
        right = [
            block
            for block in narrow
            if ((block.bbox[0] + block.bbox[2]) / 2) > page_width * 0.52
        ]

        if len(left) < 2 or len(right) < 2:
            return sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))

        top_spanning = [
            block
            for block in spanning
            if block.bbox[1]
            <= min(
                min(item.bbox[1] for item in left),
                min(item.bbox[1] for item in right),
            )
        ]
        remaining_spanning = [block for block in spanning if block not in top_spanning]
        middle = [block for block in narrow if block not in left and block not in right]

        def by_position(block: PdfTextBlock) -> tuple[float, float]:
            return block.bbox[1], block.bbox[0]

        return (
            sorted(top_spanning, key=by_position)
            + sorted(left, key=by_position)
            + sorted(right, key=by_position)
            + sorted(middle + remaining_spanning, key=by_position)
        )

    def _assess_quality(
        self,
        *,
        page: pymupdf.Page,
        blocks: list[PdfTextBlock],
        text: str,
        character_count: int,
        word_count: int,
    ) -> tuple[float, tuple[str, ...]]:
        issues: list[str] = []
        score = 1.0

        if character_count < self._min_chars_per_page:
            issues.append("too_little_text")
            score -= 0.6

        if word_count < 10:
            issues.append("too_few_words")
            score -= 0.25

        visible_characters = [
            character for character in text if not character.isspace()
        ]
        readable_ratio = (
            sum(character.isalnum() for character in visible_characters)
            / len(visible_characters)
            if visible_characters
            else 0.0
        )
        if readable_ratio < 0.55:
            issues.append("low_readable_character_ratio")
            score -= 0.35

        if blocks and word_count / len(blocks) < 2.0:
            issues.append("fragmented_text")
            score -= 0.2

        page_area = max(float(page.rect.width * page.rect.height), 1.0)
        image_area = 0.0
        try:
            for image in page.get_images(full=True):
                for rect in page.get_image_rects(image[0]):
                    image_area += max(float(rect.width * rect.height), 0.0)
        except (RuntimeError, ValueError):
            logger.debug(
                "Could not calculate PDF image coverage",
                extra={"page_number": page.number + 1},
            )

        if min(image_area / page_area, 1.0) >= 0.35:
            issues.append("large_image_area")
            score -= 0.3

        return max(0.0, min(score, 1.0)), tuple(issues)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("\r\n", "\n")
        normalized = normalized.replace("\r", "\n")

        cleaned_lines = []

        for line in normalized.splitlines():
            cleaned_line = re.sub(r"[ \t]+", " ", line).strip()

            if cleaned_line:
                cleaned_lines.append(cleaned_line)

        return "\n".join(cleaned_lines)
