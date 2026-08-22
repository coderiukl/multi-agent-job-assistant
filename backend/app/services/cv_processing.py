import logging
from dataclasses import dataclass

from fastapi import UploadFile

from app.agents import CVParserAgent
from app.repositories.cv import CVRepository
from app.schemas.cv_profile import CVProfile
from app.services.cv_ingestion import CVIngestionResult, CVIngestionService
from app.services.storage import StorageService

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
        stored_file = ingestion.stored_file

        try:
            profile = await self._parser_agent.parse(ingestion.merged_text.full_text)

            await self._cv_repository.save(
                cv_id=stored_file.file_id,
                profile=profile
            )

        except Exception:
            await self._rollback(ingestion=ingestion)
            raise

        return CVProcessingResult(
            ingestion=ingestion,
            profile=profile
        )

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