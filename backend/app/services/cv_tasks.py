import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.exceptions import AppException
from app.repositories.cv import CVRepository
from app.repositories.cv_task import CVTaskRecord, CVTaskRepository
from app.schemas.cv_task import CVTaskStatus, CVTaskStatusData
from app.services.cv_processing import CVProcessingService
from app.services.storage import StorageService, StoredFile

logger = logging.getLogger(__name__)


class AuthorizedCVTaskService:
    def __init__(
        self,
        *,
        user_id: UUID,
        tasks: CVTaskRepository,
        storage: StorageService,
        profiles: CVRepository,
    ) -> None:
        self._user_id = user_id
        self._tasks = tasks
        self._storage = storage
        self._profiles = profiles

    async def enqueue(self, file: UploadFile) -> CVTaskRecord:
        stored_file = await self._storage.save(file)
        try:
            return await self._tasks.enqueue(
                user_id=self._user_id,
                file=stored_file,
            )
        except Exception:
            await self._storage.delete(stored_file)
            raise

    async def get(self, task_id: UUID) -> CVTaskStatusData:
        task = await self._tasks.get_for_user(
            task_id=task_id,
            user_id=self._user_id,
        )
        profile = (
            await self._profiles.get(task.cv_id)
            if task.status == CVTaskStatus.COMPLETED
            else None
        )
        return CVTaskStatusData(
            task_id=task.task_id,
            cv_id=task.cv_id,
            file_name=task.original_filename,
            file_size=task.size_bytes,
            content_type=task.content_type,
            status=task.status,
            attempt_count=task.attempt_count,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_code=task.error_code,
            error_message=task.error_message,
            profile=profile,
        )


@dataclass(slots=True)
class CVTaskWorker:
    worker_id: str
    tasks: CVTaskRepository
    processing: CVProcessingService
    upload_dir: Path
    lease_seconds: int
    max_attempts: int
    poll_seconds: float

    async def run_forever(self) -> None:
        logger.info("CV task worker started", extra={"worker_id": self.worker_id})
        while True:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def run_once(self) -> bool:
        task = await self.tasks.claim_next(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            max_attempts=self.max_attempts,
        )
        if task is None:
            return False

        stored_file = StoredFile(
            file_id=task.cv_id,
            path=self.upload_dir / f"{task.cv_id}.pdf",
            original_filename=task.original_filename,
            content_type=task.content_type,
            size_bytes=task.size_bytes,
        )
        try:
            await self.processing.process_stored(stored_file)
            await self.tasks.mark_completed(
                task_id=task.task_id,
                worker_id=self.worker_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            is_retryable = not isinstance(exc, AppException) or exc.status_code >= 500
            retry = is_retryable and task.attempt_count < self.max_attempts
            error_code = (
                exc.code if isinstance(exc, AppException) else type(exc).__name__
            )
            message = (
                exc.message
                if isinstance(exc, AppException)
                else "CV processing failed."
            )
            await self.tasks.mark_failed(
                task_id=task.task_id,
                worker_id=self.worker_id,
                error_code=error_code,
                error_message=message,
                retry=retry,
                retry_delay_seconds=min(2**task.attempt_count, 60),
            )
            logger.exception(
                "CV processing task failed",
                extra={
                    "task_id": str(task.task_id),
                    "cv_id": task.cv_id,
                    "will_retry": retry,
                },
            )
        return True
