import logging
from dataclasses import dataclass

from fastapi import UploadFile


from app.services.pdf import (
    NativePdfTextExtractor,
    NativeTextExtractionResult,
    OcrTextExtractionResult,
    PdfInspectionResult,
    PdfInspector,
    PdfOcrExtractor,
    PdfTextMergeResult,
    PdfTextMerger
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
        text_merger: PdfTextMerger
    ) -> None:
        self._storage = storage
        self._pdf_inspector = pdf_inspector
        self._text_extractor = text_extractor
        self._ocr_extractor = ocr_extractor
        self._text_merger = text_merger

    async def ingest(self, upload_file: UploadFile) -> CVIngestionResult:
        stored_file = await self._storage.save(upload_file)

        try:
            inspection = await self._pdf_inspector.inspect(stored_file.path)
            extraction = await self._text_extractor.extract(stored_file.path)
            ocr_extraction = await self._ocr_extractor.extract(file_path=stored_file.path, page_numbers=extraction.ocr_required_page_numbers)
            merged_text = self._text_merger.merge(
                native_result=extraction,
                ocr_result=ocr_extraction,
            )
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

        return CVIngestionResult(
            stored_file=stored_file,
            inspection=inspection,
            extraction=extraction,
            ocr_extraction=ocr_extraction,
            merged_text=merged_text,
        )
