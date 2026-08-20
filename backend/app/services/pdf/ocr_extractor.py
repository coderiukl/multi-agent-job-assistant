from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

import numpy as np
import pymupdf

from app.core.config import Settings
from app.core.exceptions import FileValidationException, OcrProcessingException

from app.services.pdf.models import (
    OcrPageText,
    OcrTextExtractionResult,
    OcrTextLine
)

logger = logging.getLogger(__name__)

os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")

if TYPE_CHECKING:
    from paddleocr import PaddleOCR


class PdfOcrExtractor:
    def __init__(self, settings: Settings) -> None:
        self._dpi = settings.ocr_dpi
        self._min_confidence = settings.ocr_min_confidence

        self._engine: PaddleOCR | None = None
        self._engine_lock = Lock()

    async def extract(self, file_path: Path, page_numbers: tuple[int, ...]) -> OcrTextExtractionResult:
        if not page_numbers:
            return self._empty_result()

        return await asyncio.to_thread(
            self._extract_sync,
            file_path,
            page_numbers
        )

    def _extract_sync(self, file_path: Path, page_numbers: tuple[int, ...]) -> OcrTextExtractionResult:
        if not file_path.is_file():
            raise FileValidationException(
                message="PDF file does not exist.",
                details={"file_path": str(file_path)},
            )

        try:
            with pymupdf.open(str(file_path)) as document:
                self._validate_page_numbers(
                    page_numbers=page_numbers,
                    page_count=document.page_count,
                )

                pages = tuple(
                    self._extract_page(
                        page=document.load_page(page_number - 1),
                        page_number=page_number,
                    )
                    for page_number in page_numbers
                )
        except FileValidationException:
            raise

        except OcrProcessingException:
            raise

        except (pymupdf.EmptyFileError, pymupdf.FileDataError, OSError, RuntimeError, ValueError) as exc:
            logger.exception(
                "PDF OCR extraction failed",
                extra={
                    "file_path": str(file_path),
                    "error_type": type(exc).__name__,
                },
            )

            raise OcrProcessingException(
                details={
                    "reason": type(exc).__name__,
                },
            ) from exc

        full_text = "\n\n".join(
            page.text for page in pages if page.text
        )

        total_character_count = sum(
            page.character_count for page in pages
        )

        total_word_count = sum(
            page.word_count for page in pages
        )

        result = OcrTextExtractionResult(
            pages=pages,
            full_text=full_text,
            total_character_count=total_character_count,
            total_word_count=total_word_count,
            ocr_page_count=len(pages),
        )

        logger.info(
            "PDF OCR extraction completed",
            extra={
                "file_path": str(file_path),
                "ocr_page_count": len(pages),
                "character_count": total_character_count,
                "word_count": total_word_count,
            },
        )

        return result

    def _extract_page(self, *, page: pymupdf.Page, page_number: int) -> OcrPageText:
        pixmap = page.get_pixmap(
            dpi=self._dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
        )

        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)

        prediction_results = self._predict(image)

        lines: list[OcrTextLine] = []

        for prediction_result in prediction_results:
            payload = self._prediction_payload(prediction_result)
            result_data = payload.get("res", payload)

            texts = result_data.get("rec_texts", [])
            scores = result_data.get("rec_scores", [])
            boxes = result_data.get("rec_boxes", [])

            for text, score, box in zip(texts, scores, boxes, strict=False):
                normalized_text = self._normalize_text(str(text))
                confidence = float(score)

                if not normalized_text or confidence < self._min_confidence:
                    continue

                lines.append(
                    OcrTextLine(
                        text=normalized_text,
                        confidence=confidence,
                        bbox=(
                            float(box[0]),
                            float(box[1]),
                            float(box[2]),
                            float(box[3]),
                        ),
                    )
                )

        lines.sort(
            key=lambda line: (line.bbox[1], line.bbox[0])
        )

        page_text = "\n".join(line.text for line in lines)

        character_count = sum(
            1
            for character in page_text
            if not character.isspace()
        )

        word_count = len(page_text.split())

        average_confidence = (
            sum(line.confidence for line in lines)
            / len(lines)
            if lines
            else 0.0
        )

        return OcrPageText(
            page_number=page_number,
            text=page_text,
            lines=tuple(lines),
            character_count=character_count,
            word_count=word_count,
            average_confidence=average_confidence,
        )

    def _predict(self, image: np.ndarray[Any, Any]) -> list[Any]:
        with self._engine_lock:
            if self._engine is None:
                from paddleocr import PaddleOCR

                self._engine = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )

            try:
                return list(
                    self._engine.predict(
                        input=image,
                        text_rec_score_thresh=(
                            self._min_confidence
                        ),
                    )
                )

            except Exception as exc:
                raise OcrProcessingException(
                    details={
                        "reason": type(exc).__name__,
                    },
                ) from exc

    @staticmethod
    def _prediction_payload(prediction_result: Any) -> dict[str, Any]:
        if isinstance(prediction_result, dict):
            return prediction_result

        json_payload = getattr(prediction_result, "json", None)

        if isinstance(json_payload, dict):
            return json_payload

        if callable(json_payload):
            payload = json_payload()

            if isinstance(payload, dict):
                return payload

        raise OcrProcessingException(
            details={
                "reason": "INVALID_OCR_RESULT",
                "result_type": type(prediction_result).__name__,
            },
        )

    @staticmethod
    def _validate_page_numbers(*, page_numbers: tuple[int, ...], page_count: int) -> None:
        invalid_page_numbers = [
            page_number
            for page_number in page_numbers
            if page_number < 1 or page_number > page_count
        ]

        if invalid_page_numbers:
            raise FileValidationException(
                message="Invalid OCR page numbers.",
                details={
                    "invalid_page_numbers": (
                        invalid_page_numbers
                    ),
                },
            )

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)

        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _empty_result() -> OcrTextExtractionResult:
        return OcrTextExtractionResult(
            pages=(),
            full_text="",
            total_character_count=0,
            total_word_count=0,
            ocr_page_count=0,
        )
