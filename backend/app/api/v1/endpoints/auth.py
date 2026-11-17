from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestFormStrict

from app.api.auth_dependencies import (
    AuthServiceDependency,
    CurrentUserDependency,
)
from app.api.rate_limit_dependencies import (
    LoginThrottleDependency,
    require_register_quota,
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
    dependencies=[Depends(require_register_quota)],
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
    throttle: LoginThrottleDependency,
) -> AccessTokenData:
    throttle.ensure_allowed(form.username)

    try:
        result = await service.login(
            email=form.username,
            password=form.password,
        )
    except HTTPException as error:
        if error.status_code == status.HTTP_401_UNAUTHORIZED:
            throttle.record_failure(form.username)
        raise

    throttle.record_success(form.username)

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