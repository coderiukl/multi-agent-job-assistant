from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import UploadFile

from app.repositories.cv import CVRepository
from app.repositories.ownership import OwnershipRepository
from app.services.storage import StorageService

if TYPE_CHECKING:
    from app.services.cv_processing import (
        CVProcessingResult,
        CVProcessingService,
    )

logger = logging.getLogger(__name__)


class AuthorizedCVProcessingService:
    def __init__(
        self,
        *,
        user_id: UUID,
        processing: CVProcessingService,
        ownership: OwnershipRepository,
        cv_repository: CVRepository,
        storage: StorageService,
    ) -> None:
        self._user_id = user_id
        self._processing = processing
        self._ownership = ownership
        self._cv_repository = cv_repository
        self._storage = storage

    async def process(
        self,
        file: UploadFile,
    ) -> CVProcessingResult:
        result = await self._processing.process(file)
        stored_file = result.ingestion.stored_file

        try:
            await self._ownership.add_cv(
                cv_id=stored_file.file_id,
                user_id=self._user_id,
            )

        except Exception:
            cleanup_results = await asyncio.gather(
                self._cv_repository.delete(stored_file.file_id),
                self._storage.delete(stored_file),
                return_exceptions=True,
            )

            for failure in cleanup_results:
                if isinstance(failure, BaseException):
                    logger.error(
                        "CV ownership rollback failed",
                        extra={
                            "cv_id": stored_file.file_id,
                            "error_type": type(failure).__name__,
                        },
                    )

            raise

        return result