import logging
import time
from dataclasses import dataclass

from fastapi import UploadFile

from app.services.pdf import (
    NativePdfTextExtractor,
    NativeTextExtractionResult,
    OcrTextExtractionResult,
    PdfInspectionResult,
    PdfInspector,
    PdfOcrExtractor,
    PdfTextMerger,
    PdfTextMergeResult,
)
from app.services.storage import StorageService, StoredFile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CVIngestionResult:
    stored_file: StoredFile
    inspection: PdfInspectionResult
    extraction: NativeTextExtractionResult
    ocr_extraction: OcrTextExtractionResult
    merged_text: PdfTextMergeResult


class CVIngestionService:
    def __init__(
        self,
        *,
        storage: StorageService,
        pdf_inspector: PdfInspector,
        text_extractor: NativePdfTextExtractor,
        ocr_extractor: PdfOcrExtractor,
        text_merger: PdfTextMerger,
    ) -> None:
        self._storage = storage
        self._pdf_inspector = pdf_inspector
        self._text_extractor = text_extractor
        self._ocr_extractor = ocr_extractor
        self._text_merger = text_merger

    async def ingest(self, upload_file: UploadFile) -> CVIngestionResult:
        stored_file = await self._storage.save(upload_file)

        try:
            return await self.ingest_stored(stored_file)
        except Exception:
            try:
                await self._storage.delete(stored_file)
            except Exception:
                logger.exception(
                    "Failed to rollback CV upload",
                    extra={
                        "file_id": stored_file.file_id,
                    },
                )

            raise

    async def ingest_stored(self, stored_file: StoredFile) -> CVIngestionResult:
        started_at = time.perf_counter()
        inspection = await self._pdf_inspector.inspect(stored_file.path)
        inspection_finished_at = time.perf_counter()
        extraction = await self._text_extractor.extract(stored_file.path)
        native_extraction_finished_at = time.perf_counter()
        ocr_extraction = await self._ocr_extractor.extract(
            file_path=stored_file.path,
            page_numbers=extraction.ocr_required_page_numbers,
        )
        ocr_finished_at = time.perf_counter()
        merged_text = self._text_merger.merge(
            native_result=extraction,
            ocr_result=ocr_extraction,
        )
        finished_at = time.perf_counter()
        logger.info(
            "CV ingestion completed",
            extra={
                "cv_id": stored_file.file_id,
                "inspection_ms": round(
                    (inspection_finished_at - started_at) * 1000,
                    2,
                ),
                "native_extraction_ms": round(
                    (native_extraction_finished_at - inspection_finished_at)
                    * 1000,
                    2,
                ),
                "ocr_ms": round(
                    (ocr_finished_at - native_extraction_finished_at) * 1000,
                    2,
                ),
                "merge_ms": round((finished_at - ocr_finished_at) * 1000, 2),
                "total_ms": round((finished_at - started_at) * 1000, 2),
            },
        )
        return CVIngestionResult(
            stored_file=stored_file,
            inspection=inspection,
            extraction=extraction,
            ocr_extraction=ocr_extraction,
            merged_text=merged_text,
        )
