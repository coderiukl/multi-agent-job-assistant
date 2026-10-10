from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import AppException, StorageException
from app.database.auth_models import ConversationTurnModel
from app.database.session import JobSessionFactory

TURN_LEASE_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class TurnAcquisition:
    replay_response: dict[str, Any] | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_response is not None


class ConversationTurnRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def begin(
        self,
        *,
        turn_id: UUID,
        thread_id: UUID,
        user_id: UUID,
        operation: str,
        payload_hash: str,
    ) -> TurnAcquisition:
        now = datetime.now(UTC)

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        update(ConversationTurnModel)
                        .where(
                            ConversationTurnModel.thread_id == thread_id,
                            ConversationTurnModel.status == "processing",
                            ConversationTurnModel.lease_expires_at < now,
                        )
                        .values(
                            status="failed",
                            error_code="TURN_LEASE_EXPIRED",
                            completed_at=now,
                        )
                    )
                    session.add(
                        ConversationTurnModel(
                            turn_id=turn_id,
                            thread_id=thread_id,
                            user_id=user_id,
                            operation=operation,
                            payload_hash=payload_hash,
                            status="processing",
                            lease_expires_at=now
                            + timedelta(seconds=TURN_LEASE_SECONDS),
                        )
                    )
        except IntegrityError:
            return await self._resolve_conflict(
                turn_id=turn_id,
                thread_id=thread_id,
                user_id=user_id,
                operation=operation,
                payload_hash=payload_hash,
            )
        except SQLAlchemyError as exc:
            raise StorageException(
                message="Conversation turn could not be started."
            ) from exc

        return TurnAcquisition()

    async def complete(
        self,
        *,
        turn_id: UUID,
        response_data: dict[str, Any],
    ) -> None:
        await self._update_status(
            turn_id=turn_id,
            values={
                "status": "completed",
                "response_data": response_data,
                "completed_at": datetime.now(UTC),
                "error_code": None,
            },
        )

    async def fail(self, *, turn_id: UUID, error_code: str) -> None:
        await self._update_status(
            turn_id=turn_id,
            values={
                "status": "failed",
                "error_code": error_code[:100],
                "completed_at": datetime.now(UTC),
            },
        )

    async def _update_status(
        self, *, turn_id: UUID, values: dict[str, Any]
    ) -> None:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        update(ConversationTurnModel)
                        .where(
                            ConversationTurnModel.turn_id == turn_id,
                            ConversationTurnModel.status == "processing",
                        )
                        .values(**values)
                    )
        except SQLAlchemyError as exc:
            raise StorageException(
                message="Conversation turn status could not be stored."
            ) from exc

    async def _resolve_conflict(
        self,
        *,
        turn_id: UUID,
        thread_id: UUID,
        user_id: UUID,
        operation: str,
        payload_hash: str,
    ) -> TurnAcquisition:
        try:
            async with self._session_factory() as session:
                existing = await session.get(ConversationTurnModel, turn_id)

                if existing is None:
                    active_turn_id = await session.scalar(
                        select(ConversationTurnModel.turn_id).where(
                            ConversationTurnModel.thread_id == thread_id,
                            ConversationTurnModel.status == "processing",
                        )
                    )
                    raise AppException(
                        status_code=409,
                        code="CONVERSATION_TURN_IN_PROGRESS",
                        message=(
                            "Another request is already processing this conversation."
                        ),
                        details={"active_turn_id": str(active_turn_id)},
                    )

                same_request = (
                    existing.thread_id == thread_id
                    and existing.user_id == user_id
                    and existing.operation == operation
                    and existing.payload_hash == payload_hash
                )
                if not same_request:
                    raise AppException(
                        status_code=409,
                        code="TURN_ID_REUSED",
                        message="This turn_id was already used for another request.",
                    )

                if existing.status == "completed" and existing.response_data:
                    return TurnAcquisition(
                        replay_response=dict(existing.response_data)
                    )

                code = (
                    "CONVERSATION_TURN_IN_PROGRESS"
                    if existing.status == "processing"
                    else "CONVERSATION_TURN_FAILED"
                )
                message = (
                    "This conversation turn is still processing."
                    if existing.status == "processing"
                    else "This conversation turn previously failed; use a new turn_id."
                )
                raise AppException(
                    status_code=409,
                    code=code,
                    message=message,
                    details={"turn_id": str(turn_id)},
                )
        except AppException:
            raise
        except SQLAlchemyError as exc:
            raise StorageException(
                message="Conversation turn could not be read."
            ) from exc
