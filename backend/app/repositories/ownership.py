from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import (
    ResourceNotFoundException,
    StorageException,
)
from app.database.auth_models import (
    ConversationOwnershipModel,
    CVOwnershipModel,
)
from app.database.session import JobSessionFactory


class OwnershipRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def add_cv(self, *, cv_id: str, user_id: UUID) -> None:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(
                        CVOwnershipModel(
                            cv_id=cv_id,
                            user_id=user_id,
                        )
                    )

        except SQLAlchemyError as exc:
            raise StorageException(message="CV ownership could not be stored.") from exc

    async def require_cv(self, *, cv_id: str, user_id: UUID) -> None:
        statement = select(CVOwnershipModel.cv_id).where(
            CVOwnershipModel.cv_id == cv_id,
            CVOwnershipModel.user_id == user_id,
        )

        try:
            async with self._session_factory() as session:
                owned_cv = await session.scalar(statement)

        except SQLAlchemyError as exc:
            raise StorageException(message="CV ownership could not be read.") from exc

        if owned_cv is None:
            raise ResourceNotFoundException(
                resource="CV",
                identifier=cv_id,
            )

    async def delete_cv(self, *, cv_id: str, user_id: UUID) -> None:
        statement = delete(CVOwnershipModel).where(
            CVOwnershipModel.cv_id == cv_id,
            CVOwnershipModel.user_id == user_id,
        )

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(statement)
        except SQLAlchemyError as exc:
            raise StorageException(
                message="CV ownership could not be deleted."
            ) from exc

    async def get_thread_owner(self, thread_id: UUID) -> UUID | None:
        statement = select(ConversationOwnershipModel.user_id).where(
            ConversationOwnershipModel.thread_id == thread_id
        )

        try:
            async with self._session_factory() as session:
                return await session.scalar(statement)

        except SQLAlchemyError as exc:
            raise StorageException(
                message="Conversation ownership could not be read."
            ) from exc

    async def list_threads_for_user(
        self,
        user_id: UUID,
    ) -> list[tuple[UUID, datetime]]:
        statement = (
            select(
                ConversationOwnershipModel.thread_id,
                ConversationOwnershipModel.created_at,
            )
            .where(ConversationOwnershipModel.user_id == user_id)
            .order_by(ConversationOwnershipModel.created_at.desc())
        )

        try:
            async with self._session_factory() as session:
                rows = (await session.execute(statement)).all()

        except SQLAlchemyError as exc:
            raise StorageException(
                message="Conversation ownerships could not be read."
            ) from exc

        return [(row.thread_id, row.created_at) for row in rows]

    async def require_thread(self, *, thread_id: UUID, user_id: UUID) -> None:
        if await self.get_thread_owner(thread_id) != user_id:
            raise ResourceNotFoundException(
                resource="Conversation",
                identifier=str(thread_id),
            )

    async def claim_thread(self, *, thread_id: UUID, user_id: UUID) -> None:
        statement = (
            insert(ConversationOwnershipModel)
            .values(
                thread_id=thread_id,
                user_id=user_id,
            )
            .on_conflict_do_nothing(
                index_elements=[ConversationOwnershipModel.thread_id]
            )
        )

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(statement)

                    owner = await session.scalar(
                        select(ConversationOwnershipModel.user_id).where(
                            ConversationOwnershipModel.thread_id == thread_id
                        )
                    )

                    if owner != user_id:
                        raise ResourceNotFoundException(
                            resource="Conversation",
                            identifier=str(thread_id),
                        )

        except SQLAlchemyError as exc:
            raise StorageException(
                message="Conversation ownership could not be stored."
            ) from exc
