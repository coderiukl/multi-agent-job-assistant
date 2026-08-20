import logging
from dataclasses import dataclass

from fastapi import UploadFile

from app.agents import CVParserAgent
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
    ) -> None:
        self._ingestion_service = ingestion_service
        self._parser_agent = parser_agent
        self._storage_service = storage_service

    async def process(self, upload_file: UploadFile) -> CVProcessingResult:
        ingestion = await self._ingestion_service.ingest(upload_file)

        try:
            profile = await self._parser_agent.parse(ingestion.merged_text.full_text)

        except Exception:
            try:
                await self._storage_service.delete(ingestion.stored_file)
            except Exception:
                logger.exception(
                    "Failed to rollback CV after parsing error",
                    extra={
                        "file_id": (
                            ingestion.stored_file.file_id
                        ),
                    },
                )

            raise

        return CVProcessingResult(
            ingestion=ingestion,
            profile=profile
        )