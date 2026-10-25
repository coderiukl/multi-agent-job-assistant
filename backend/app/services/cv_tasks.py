import asyncio
import logging
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
        retention_days: int,
    ) -> None:
        self._user_id = user_id
        self._tasks = tasks
        self._storage = storage
        self._profiles = profiles
        self._retention_days = retention_days

    async def enqueue(self, files: list[UploadFile]) -> CVTaskRecord:
        stored_file = await self._storage.save_many(files)
        try:
            return await self._tasks.enqueue(
                user_id=self._user_id,
                file=stored_file,
                retention_expires_at=(
                    datetime.now(UTC) + timedelta(days=self._retention_days)
                ),
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
    heartbeat_seconds: int
    timeout_seconds: int
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

        heartbeat = asyncio.create_task(
            self._renew_lease_until_finished(task.task_id),
            name=f"cv-task-heartbeat-{task.task_id}",
        )

        stored_file = StoredFile(
            file_id=task.cv_id,
            path=self.upload_dir / f"{task.cv_id}.pdf",
            original_filename=task.original_filename,
            content_type=task.content_type,
            size_bytes=task.size_bytes,
        )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self.processing.process_stored(stored_file)
            await self.tasks.mark_completed(
                task_id=task.task_id,
                worker_id=self.worker_id,
            )
        except TimeoutError:
            retry = task.attempt_count < self.max_attempts
            await self.tasks.mark_failed(
                task_id=task.task_id,
                worker_id=self.worker_id,
                error_code="PROCESSING_TIMEOUT",
                error_message=(
                    f"CV processing exceeded {self.timeout_seconds} seconds."
                ),
                retry=retry,
                retry_delay_seconds=min(2**task.attempt_count, 60),
            )
            logger.error(
                "CV processing timed out; recycling worker",
                extra={
                    "task_id": str(task.task_id),
                    "cv_id": task.cv_id,
                    "duration_ms": self.timeout_seconds * 1000,
                    "will_retry": retry,
                },
            )
            logging.shutdown()
            os.kill(os.getpid(), signal.SIGTERM)
            return True
        except asyncio.CancelledError:
            await self.tasks.mark_failed(
                task_id=task.task_id,
                worker_id=self.worker_id,
                error_code="WORKER_STOPPED",
                error_message="CV worker stopped before processing completed.",
                retry=True,
                retry_delay_seconds=0,
            )
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
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
        return True

    async def _renew_lease_until_finished(self, task_id: UUID) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                renewed = await self.tasks.renew_lease(
                    task_id=task_id,
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                logger.exception(
                    "CV processing task heartbeat failed",
                    extra={"task_id": str(task_id)},
                )
                continue

            if not renewed:
                logger.warning(
                    "CV processing task lease is no longer owned by this worker",
                    extra={"task_id": str(task_id)},
                )
                return
