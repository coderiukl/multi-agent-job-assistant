from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.core.auth_config import AuthSettings
from app.core.exceptions import AppException
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    password_hasher,
    unauthorized,
)
from app.repositories.user import UserRepository
from app.schemas.auth import (
    AccessTokenData,
    RegisterRequest,
    UserData,
)


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        settings: AuthSettings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    async def register(self, request: RegisterRequest) -> UserData:
        email = str(request.email).lower()

        if await self._repository.get_by_email(email) is not None:
            raise AppException(
                status_code=409,
                code="EMAIL_ALREADY_REGISTERED",
                message="This email is already registered.",
            )

        password_hash = await run_in_threadpool(
            password_hasher.hash,
            request.password.get_secret_value(),
        )

        user = await self._repository.create(
            email=email,
            password_hash=password_hash,
        )

        return UserData.model_validate(user)

    async def login(self, *, email: str, password: str) -> AccessTokenData:
        if len(email) > 254 or not 1 <= len(password) <= 128:
            raise unauthorized()

        user = await self._repository.get_by_email(
            email.strip().lower()
        )

        stored_hash = (
            user.password_hash
            if user
            else DUMMY_PASSWORD_HASH
        )

        verified = await run_in_threadpool(
            password_hasher.verify,
            password,
            stored_hash,
        )

        if user is None or not verified or not user.is_active:
            raise unauthorized()

        return AccessTokenData(
            access_token=create_access_token(
                user.user_id,
                self._settings,
            ),
            expires_in=self._settings.auth_access_token_minutes * 60,
        )

    async def get_active_user(self, user_id: UUID) -> UserData:
        user = await self._repository.get_by_id(user_id)

        if user is None or not user.is_active:
            raise unauthorized()

        return UserData.model_validate(user)