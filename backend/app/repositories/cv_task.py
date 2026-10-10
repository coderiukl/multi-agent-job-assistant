from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ResourceNotFoundException, StorageException
from app.database.auth_models import CVOwnershipModel, CVProcessingTaskModel
from app.database.session import JobSessionFactory
from app.schemas.cv_task import CVTaskStatus
from app.services.storage import StoredFile


@dataclass(frozen=True, slots=True)
class CVTaskRecord:
    task_id: UUID
    cv_id: str
    user_id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: CVTaskStatus
    attempt_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None


class CVTaskRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def enqueue(self, *, user_id: UUID, file: StoredFile) -> CVTaskRecord:
        task_id = uuid4()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(CVOwnershipModel(cv_id=file.file_id, user_id=user_id))
                    task = CVProcessingTaskModel(
                        task_id=task_id,
                        cv_id=file.file_id,
                        user_id=user_id,
                        original_filename=file.original_filename,
                        content_type=file.content_type,
                        size_bytes=file.size_bytes,
                        status=CVTaskStatus.PENDING.value,
                    )
                    session.add(task)
                await session.refresh(task)
        except SQLAlchemyError as exc:
            raise StorageException(
                message="CV processing task could not be created."
            ) from exc

        return self._to_record(task)

    async def get_for_user(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> CVTaskRecord:
        statement = select(CVProcessingTaskModel).where(
            CVProcessingTaskModel.task_id == task_id,
            CVProcessingTaskModel.user_id == user_id,
        )
        try:
            async with self._session_factory() as session:
                task = await session.scalar(statement)
        except SQLAlchemyError as exc:
            raise StorageException(
                message="CV processing task could not be read."
            ) from exc

        if task is None:
            raise ResourceNotFoundException(
                resource="CV processing task",
                identifier=str(task_id),
            )
        return self._to_record(task)

    async def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> CVTaskRecord | None:
        now = datetime.now(UTC)
        claimable = or_(
            CVProcessingTaskModel.status == CVTaskStatus.PENDING.value,
            (
                (CVProcessingTaskModel.status == CVTaskStatus.PROCESSING.value)
                & (CVProcessingTaskModel.lease_expires_at < now)
            ),
        )
        statement = (
            select(CVProcessingTaskModel)
            .where(
                claimable,
                CVProcessingTaskModel.available_at <= now,
                CVProcessingTaskModel.attempt_count < max_attempts,
            )
            .order_by(
                CVProcessingTaskModel.available_at,
                CVProcessingTaskModel.created_at,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        update(CVProcessingTaskModel)
                        .where(
                            CVProcessingTaskModel.status
                            == CVTaskStatus.PROCESSING.value,
                            CVProcessingTaskModel.lease_expires_at < now,
                            CVProcessingTaskModel.attempt_count >= max_attempts,
                        )
                        .values(
                            status=CVTaskStatus.FAILED.value,
                            completed_at=now,
                            lease_owner=None,
                            lease_expires_at=None,
                            error_code="MAX_ATTEMPTS_EXCEEDED",
                            error_message=(
                                "CV processing stopped after the maximum "
                                "number of attempts."
                            ),
                        )
                    )
                    task = await session.scalar(statement)
                    if task is None:
                        return None
                    task.status = CVTaskStatus.PROCESSING.value
                    task.attempt_count += 1
                    task.started_at = task.started_at or now
                    task.lease_owner = worker_id
                    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
                    task.error_code = None
                    task.error_message = None
                await session.refresh(task)
        except SQLAlchemyError as exc:
            raise StorageException(
                message="CV processing task could not be claimed."
            ) from exc

        return self._to_record(task)

    async def mark_completed(self, *, task_id: UUID, worker_id: str) -> None:
        await self._finish(
            task_id=task_id,
            worker_id=worker_id,
            status=CVTaskStatus.COMPLETED,
        )

    async def mark_failed(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error_code: str,
        error_message: str,
        retry: bool,
        retry_delay_seconds: int,
    ) -> None:
        now = datetime.now(UTC)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    task = await session.scalar(
                        select(CVProcessingTaskModel)
                        .where(
                            CVProcessingTaskModel.task_id == task_id,
                            CVProcessingTaskModel.status
                            == CVTaskStatus.PROCESSING.value,
                            CVProcessingTaskModel.lease_owner == worker_id,
                        )
                        .with_for_update()
                    )
                    if task is None:
                        return
                    task.status = (
                        CVTaskStatus.PENDING.value
                        if retry
                        else CVTaskStatus.FAILED.value
                    )
                    task.available_at = now + timedelta(seconds=retry_delay_seconds)
                    task.error_code = error_code[:100]
                    task.error_message = error_message[:1000]
                    task.lease_owner = None
                    task.lease_expires_at = None
                    task.completed_at = None if retry else now
        except SQLAlchemyError as exc:
            raise StorageException(
                message="CV processing task failure could not be recorded."
            ) from exc

    async def _finish(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        status: CVTaskStatus,
    ) -> None:
        now = datetime.now(UTC)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    task = await session.scalar(
                        select(CVProcessingTaskModel)
                        .where(
                            CVProcessingTaskModel.task_id == task_id,
                            CVProcessingTaskModel.status
                            == CVTaskStatus.PROCESSING.value,
                            CVProcessingTaskModel.lease_owner == worker_id,
                        )
                        .with_for_update()
                    )
                    if task is None:
                        return
                    task.status = status.value
                    task.completed_at = now
                    task.lease_owner = None
                    task.lease_expires_at = None
                    task.error_code = None
                    task.error_message = None
        except SQLAlchemyError as exc:
            raise StorageException(
                message="CV processing task could not be completed."
            ) from exc

    @staticmethod
    def _to_record(task: CVProcessingTaskModel) -> CVTaskRecord:
        return CVTaskRecord(
            task_id=task.task_id,
            cv_id=task.cv_id,
            user_id=task.user_id,
            original_filename=task.original_filename,
            content_type=task.content_type,
            size_bytes=task.size_bytes,
            status=CVTaskStatus(task.status),
            attempt_count=task.attempt_count,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_code=task.error_code,
            error_message=task.error_message,
        )
