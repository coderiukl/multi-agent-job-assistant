from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import AppException, StorageException
from app.database.auth_models import UserModel
from app.database.session import JobSessionFactory


class UserRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def get_by_email(self, email: str) -> UserModel | None:
        statement = select(UserModel).where(UserModel.email == email)
        return await self._get(statement)

    async def get_by_id(self, user_id: UUID) -> UserModel | None:
        statement = select(UserModel).where(UserModel.user_id == user_id)
        return await self._get(statement)

    async def _get(self, statement: Select[tuple[UserModel]]) -> UserModel | None:
        try:
            async with self._session_factory() as session:
                return await session.scalar(statement)

        except SQLAlchemyError as exc:
            raise StorageException(
                message="User data could not be read."
            ) from exc

    async def create(self, *, email: str, password_hash: str) -> UserModel:
        user = UserModel(
            email=email,
            password_hash=password_hash,
        )

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(user)
                    await session.flush()
                    await session.refresh(user)

            return user

        except IntegrityError as exc:
            cause = getattr(exc.orig, "__cause__", None)

            if getattr(cause, "constraint_name", None) == "uq_users_email":
                raise AppException(
                    status_code=409,
                    code="EMAIL_ALREADY_REGISTERED",
                    message="This email is already registered.",
                ) from exc

            raise StorageException(
                message="User account could not be stored."
            ) from exc

        except SQLAlchemyError as exc:
            raise StorageException(
                message="User account could not be stored."
            ) from exc