from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.auth_config import AuthSettings, get_auth_settings
from app.core.config import get_settings
from app.core.security import decode_access_token, unauthorized
from app.repositories.user import UserRepository
from app.schemas.auth import UserData
from app.services.auth import AuthService

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_prefix}/auth/login",
    auto_error=False,
)

AuthSettingsDependency = Annotated[
    AuthSettings,
    Depends(get_auth_settings),
]


def get_auth_service(settings: AuthSettingsDependency) -> AuthService:
    from app.api.dependencies import get_job_session_factory

    return AuthService(
        repository=UserRepository(get_job_session_factory()),
        settings=settings,
    )


AuthServiceDependency = Annotated[
    AuthService,
    Depends(get_auth_service),
]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    service: AuthServiceDependency,
    settings: AuthSettingsDependency,
) -> UserData:
    if token is None:
        raise unauthorized()

    user_id = decode_access_token(token, settings)

    return await service.get_active_user(user_id)


CurrentUserDependency = Annotated[
    UserData,
    Depends(get_current_user),
]