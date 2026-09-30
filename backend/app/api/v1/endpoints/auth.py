from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestFormStrict

from app.api.auth_dependencies import (
    AuthServiceDependency,
    CurrentUserDependency,
)
from app.schemas.auth import (
    AccessTokenData,
    RegisterRequest,
    UserData,
)
from app.schemas.response import ApiResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=ApiResponse[UserData],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    service: AuthServiceDependency,
) -> ApiResponse[UserData]:
    user = await service.register(request)

    return ApiResponse(
        message="Account created successfully.",
        data=user,
    )


@router.post(
    "/login",
    response_model=AccessTokenData,
)
async def login(
    response: Response,
    form: Annotated[
        OAuth2PasswordRequestFormStrict,
        Depends(),
    ],
    service: AuthServiceDependency,
) -> AccessTokenData:
    result = await service.login(
        email=form.username,
        password=form.password,
    )

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return result


@router.get(
    "/me",
    response_model=ApiResponse[UserData],
)
async def me(
    user: CurrentUserDependency,
) -> ApiResponse[UserData]:
    return ApiResponse(data=user)