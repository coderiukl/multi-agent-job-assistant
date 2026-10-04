from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.auth_dependencies import get_auth_service, get_auth_settings
from app.api.v1.endpoints.auth import router
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppException
from app.core.security import create_access_token, decode_access_token, password_hasher
from app.schemas.auth import RegisterRequest
from app.services.auth import AuthService


@pytest.fixture
def service(user_repository, auth_settings):
    return AuthService(user_repository, auth_settings)


@pytest.fixture
def client(service, auth_settings):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1/auth")
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_auth_settings] = lambda: auth_settings
    with TestClient(app) as client:
        yield client


async def test_register_hashes_password(service, user_repository):
    user_repository.get_by_email.return_value = None
    request = RegisterRequest(email=" ALICE@example.com ", password="Password-12345")
    result = await service.register(request)
    kwargs = user_repository.create.call_args.kwargs
    assert kwargs["email"] == "alice@example.com"
    assert kwargs["password_hash"] != "Password-12345"
    assert password_hasher.verify("Password-12345", kwargs["password_hash"])
    assert "password_hash" not in result.model_dump()


async def test_duplicate_registration(service, user_repository):
    with pytest.raises(AppException) as exc:
        await service.register(RegisterRequest(
            email="alice@example.com", password="Password-12345"
        ))
    assert exc.value.status_code == 409
    user_repository.create.assert_not_awaited()


@pytest.mark.parametrize("case", ["missing", "wrong_password", "inactive"])
async def test_login_rejected(case, service, user, user_repository):
    user.password_hash = password_hasher.hash("Password-12345")
    if case == "missing":
        user_repository.get_by_email.return_value = None
    if case == "inactive":
        user.is_active = False
    with pytest.raises(HTTPException) as exc:
        await service.login(
            email="alice@example.com",
            password="Wrong-password" if case == "wrong_password" else "Password-12345",
        )
    assert exc.value.status_code == 401


def test_login_and_me(client, user, auth_settings):
    user.password_hash = password_hasher.hash("Password-12345")
    response = client.post("/api/v1/auth/login", data={
        "grant_type": "password", "username": user.email, "password": "Password-12345",
    })
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["access_token"]
    assert decode_access_token(token, auth_settings) == user.user_id
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["user_id"] == str(user.user_id)


@pytest.mark.parametrize("token", [None, "invalid.jwt.token"])
def test_me_requires_valid_token(client, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("case", ["expired", "issuer", "audience", "type", "subject", "signature"])
def test_invalid_claims_rejected(case, user, auth_settings):
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.user_id), "iat": now, "exp": now + timedelta(minutes=5),
        "iss": auth_settings.auth_jwt_issuer, "aud": auth_settings.auth_jwt_audience,
        "token_type": "access",
    }
    changes = {
        "expired": {"exp": now - timedelta(seconds=1)}, "issuer": {"iss": "other"},
        "audience": {"aud": "other"}, "type": {"token_type": "refresh"},
        "subject": {"sub": "not-a-uuid"},
    }
    payload.update(changes.get(case, {}))
    key = "another-secret-that-is-at-least-32-bytes" if case == "signature" else auth_settings.auth_jwt_secret.get_secret_value()
    token = jwt.encode(payload, key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token, auth_settings)
    assert exc.value.status_code == 401


def test_inactive_user_token_rejected(client, user, auth_settings):
    token = create_access_token(user.user_id, auth_settings)
    user.is_active = False
    assert client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {token}"
    }).status_code == 401


def test_password_not_leaked_in_validation_error(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "invalid", "password": "secret-short",
    })
    assert response.status_code == 422
    assert "secret-short" not in response.text
