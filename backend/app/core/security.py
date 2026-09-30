from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import HTTPException
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.auth_config import AuthSettings

password_hasher = PasswordHash.recommended()

DUMMY_PASSWORD_HASH = password_hasher.hash(
    "dummy-password-for-timing-check"
)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Invalid credentials or access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(user_id: UUID, settings: AuthSettings) -> str:
    now = datetime.now(UTC)

    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.auth_access_token_minutes),
            "iss": settings.auth_jwt_issuer,
            "aud": settings.auth_jwt_audience,
            "token_type": "access",
        },
        settings.auth_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: AuthSettings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            options={
                "require": [
                    "sub",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                    "token_type",
                ]
            },
        )

        if payload["token_type"] != "access":
            raise ValueError("Invalid token type.")

        if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
            raise ValueError("Invalid token timestamps.")

        return UUID(payload["sub"])

    except (InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        raise unauthorized() from exc