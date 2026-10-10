import logging
import re
import unicodedata
from dataclasses import dataclass

from fastapi import UploadFile

from app.agents import CVParserAgent
from app.repositories.cv import CVRepository
from app.schemas.cv_profile import CVProfile
from app.services.cv_ingestion import CVIngestionResult, CVIngestionService
from app.services.storage import StorageService, StoredFile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CVProcessingResult:
    ingestion: CVIngestionResult
    profile: CVProfile


class CVProcessingService:
    def __init__(
        self,
        *,
        ingestion_service: CVIngestionService,
        parser_agent: CVParserAgent,
        storage_service: StorageService,
        cv_repository: CVRepository,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._parser_agent = parser_agent
        self._storage_service = storage_service
        self._cv_repository = cv_repository

    async def process(self, upload_file: UploadFile) -> CVProcessingResult:
        ingestion = await self._ingestion_service.ingest(upload_file)

        try:
            return await self._process_ingestion(ingestion)
        except Exception:
            await self._rollback(ingestion=ingestion)
            raise

    async def process_stored(self, stored_file: StoredFile) -> CVProcessingResult:
        ingestion = await self._ingestion_service.ingest_stored(stored_file)
        try:
            return await self._process_ingestion(ingestion)
        except Exception:
            await self._cv_repository.delete(stored_file.file_id)
            raise

    async def _process_ingestion(
        self,
        ingestion: CVIngestionResult,
    ) -> CVProcessingResult:
        stored_file = ingestion.stored_file
        parser_text = "\n\n".join(
            (
                f'<PAGE number="{page.page_number}" '
                f'extraction_method="{page.method}">\n'
                f"{page.text}\n</PAGE>"
            )
            for page in ingestion.merged_text.pages
            if page.text
        )
        profile = await self._parser_agent.parse(parser_text)

        method_by_page = {
            page.page_number: page.method for page in ingestion.merged_text.pages
        }
        source_by_page = {
            page.page_number: self._normalize_evidence(page.text)
            for page in ingestion.merged_text.pages
        }
        native_quality_by_page = {
            page.page_number: page.quality_score for page in ingestion.extraction.pages
        }
        ocr_quality_by_page = {
            page.page_number: page.average_confidence
            for page in ingestion.ocr_extraction.pages
        }
        verified_provenance = []
        for evidence in profile.provenance:
            page_source = source_by_page.get(evidence.page_number, "")
            normalized_excerpt = self._normalize_evidence(evidence.source_text)
            if not normalized_excerpt or normalized_excerpt not in page_source:
                continue

            method = method_by_page.get(evidence.page_number)
            extraction_confidence = (
                ocr_quality_by_page.get(evidence.page_number, 0.0)
                if method == "ocr"
                else native_quality_by_page.get(evidence.page_number, 0.0)
            )
            verified_provenance.append(
                evidence.model_copy(
                    update={
                        "confidence": min(
                            evidence.confidence,
                            extraction_confidence,
                        ),
                        "extraction_method": method,
                    }
                )
            )

        expected_evidence_count = (
            len(profile.skills)
            + len(profile.work_experiences)
            + len(profile.educations)
        )
        profile = profile.model_copy(
            update={
                "provenance": verified_provenance,
                "needs_review": (
                    profile.needs_review
                    or any(
                        evidence.confidence < 0.7 for evidence in verified_provenance
                    )
                    or len(verified_provenance) < expected_evidence_count
                ),
            }
        )

        await self._cv_repository.save(cv_id=stored_file.file_id, profile=profile)

        return CVProcessingResult(ingestion=ingestion, profile=profile)

    @staticmethod
    def _normalize_evidence(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return re.sub(r"\s+", " ", normalized).strip()

    async def _rollback(self, *, ingestion: CVIngestionResult) -> None:
        cv_id = ingestion.stored_file.file_id

        try:
            await self._cv_repository.delete(cv_id)
        except Exception:
            logger.exception(
                "Failed to rollback CV profile",
                extra={"cv_id": cv_id},
            )

        try:
            await self._storage_service.delete(ingestion.stored_file)
        except Exception:
            logger.exception(
                "Failed to rollback CV file",
                extra={"cv_id": cv_id},
            )
