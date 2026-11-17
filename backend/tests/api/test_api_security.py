"""FastAPI endpoint, authentication and security tests (Phase 5).

The real FastAPI app (routers, middleware, exception handlers, auth
dependencies, AuthorizedConversationService) is exercised through
httpx.ASGITransport. The application lifespan is NOT started, so no database
pool or checkpointer connection is opened; data-layer collaborators are
in-memory fakes injected via ``app.dependency_overrides``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import jwt
import pytest

from app.api.auth_dependencies import CurrentUserDependency, get_auth_service
from app.api.dependencies import get_job_search_service
from app.api.rate_limit_dependencies import reset_rate_limiters
from app.api.resource_dependencies import get_authorized_conversation_service
from app.core.auth_config import get_auth_settings
from app.core.security import create_access_token, password_hasher
from app.main import app
from app.schemas.conversations_intent import ConversationIntent as I
from app.services.auth import AuthService
from app.services.authorized_conversation import AuthorizedConversationService
from tests.conftest import (
    FakeJobSearchService,
    GraphHarness,
    InMemoryOwnership,
    InMemoryTurns,
    intent,
)

API = "/api/v1"


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, SimpleNamespace] = {}

    def add(self, email: str, password: str, active: bool = True) -> SimpleNamespace:
        user = SimpleNamespace(user_id=uuid4(), email=email,
                               password_hash=password_hasher.hash(password),
                               is_active=active, created_at=datetime.now(UTC))
        self.users[email] = user
        return user

    async def get_by_email(self, email):
        return self.users.get(email)

    async def get_by_id(self, user_id):
        return next((u for u in self.users.values() if u.user_id == user_id), None)

    async def create(self, *, email, password_hash):
        return self.add(email, "unused-password-123")


class Env:
    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.alice = self.users.add("alice@example.com", "correct-horse-battery")
        self.bob = self.users.add("bob@example.com", "correct-horse-battery")
        self.harness = GraphHarness()
        self.ownership = InMemoryOwnership()
        self.turns = InMemoryTurns()
        self.search = FakeJobSearchService()
        settings = get_auth_settings()

        def auth_service():
            return AuthService(repository=self.users, settings=settings)

        app.dependency_overrides[get_auth_service] = auth_service
        app.dependency_overrides[get_job_search_service] = lambda: self.search

        # Keep the real get_current_user (JWT + active-user check) in the chain.
        async def authorized(user: CurrentUserDependency):
            return AuthorizedConversationService(
                user_id=user.user_id, service=self.harness.service, graph=self.harness.graph,
                ownership=self.ownership, turns=self.turns,
            )

        app.dependency_overrides[get_authorized_conversation_service] = authorized

    def token(self, user) -> str:
        return create_access_token(user.user_id, get_auth_settings())

    def headers(self, user) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(user)}"}


@pytest.fixture
def env():
    reset_rate_limiters()
    environment = Env()
    yield environment
    app.dependency_overrides.clear()
    reset_rate_limiters()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


# --------------------------------------------------------------------------
# System / schema
# --------------------------------------------------------------------------
async def test_api_01_health(client):
    """TC-API-01: GET /health -> 200 with the ApiResponse envelope."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["data"]["status"] == "healthy"
    assert response.headers["X-Request-ID"]


async def test_api_02_request_id_is_sanitised(client):
    """TC-API-02: a malicious X-Request-ID is replaced, a valid one echoed."""
    bad = await client.get("/health", headers={"X-Request-ID": "x\r\nSet-Cookie: a=b"})
    good = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert bad.headers["X-Request-ID"] != "x\r\nSet-Cookie: a=b"
    assert good.headers["X-Request-ID"] == "abc-123"


async def test_api_03_openapi_lists_all_routes(client):
    """TC-API-03: OpenAPI schema is generated and contains every router."""
    paths = (await client.get("/openapi.json")).json()["paths"]
    for path in ("/api/v1/auth/login", "/api/v1/cvs", "/api/v1/conversation/messages",
                 "/api/v1/conversation/resume", "/api/v1/jobs/search"):
        assert path in paths


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
PROTECTED = [
    ("GET", f"{API}/auth/me", None),
    ("GET", f"{API}/conversation/threads", None),
    ("POST", f"{API}/conversation/messages", {"message": "hi"}),
    ("POST", f"{API}/conversation/intent-analysis", {"message": "hi"}),
    ("GET", f"{API}/cvs/{'a' * 32}", None),
    ("DELETE", f"{API}/cvs/{'a' * 32}", None),
    ("GET", f"{API}/cvs/processing-tasks/{uuid4()}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
async def test_sec_01_protected_endpoints_require_token(env, client, method, path, body):
    """TC-SEC-01: protected endpoints return 401 without a bearer token."""
    response = await client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "HTTP_401"


async def test_sec_02_job_search_requires_authentication(env, client):
    """TC-SEC-02 (BUG-001 fixed): /jobs/search triggers paid LLM + embedding
    calls, so it must not be callable anonymously – and the search pipeline
    must not run before authentication."""
    response = await client.post(f"{API}/jobs/search", json={"query": "python"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert env.search.requests == []


async def test_sec_02b_job_search_works_with_token(env, client):
    """TC-SEC-02b: an authenticated search runs the pipeline -> 200."""
    response = await client.post(f"{API}/jobs/search", json={"query": "python"},
                                 headers=env.headers(env.alice))
    assert response.status_code == 200
    assert len(env.search.requests) == 1


async def test_sec_02c_job_search_rate_limited_per_user(env, client):
    """TC-SEC-02c (BUG-001): each user has a per-minute search quota; the
    quota is per user (Bob is unaffected) and 429 carries Retry-After."""
    from app.api import rate_limit_dependencies as limits

    limit = limits.get_job_search_rate_limiter().limit
    for _ in range(limit):
        ok = await client.post(f"{API}/jobs/search", json={"query": "python"},
                               headers=env.headers(env.alice))
        assert ok.status_code == 200
    blocked = await client.post(f"{API}/jobs/search", json={"query": "python"},
                                headers=env.headers(env.alice))
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert len(env.search.requests) == limit
    bob = await client.post(f"{API}/jobs/search", json={"query": "python"},
                            headers=env.headers(env.bob))
    assert bob.status_code == 200


def _forge(**claims) -> str:
    settings = get_auth_settings()
    now = int(time.time())
    payload = {"sub": str(uuid4()), "iat": now, "exp": now + 600,
               "iss": settings.auth_jwt_issuer, "aud": settings.auth_jwt_audience,
               "token_type": "access", **claims}
    return jwt.encode(payload, settings.auth_jwt_secret.get_secret_value(), algorithm="HS256")


@pytest.mark.parametrize("case", ["expired", "wrong_aud", "wrong_iss", "refresh", "bad_sig",
                                  "alg_none", "garbage", "unknown_user"])
async def test_sec_03_invalid_tokens_rejected(env, client, case):
    """TC-SEC-03: tampered/expired/foreign JWTs -> 401."""
    alice = str(env.alice.user_id)
    tokens = {
        "expired": _forge(sub=alice, exp=int(time.time()) - 10),
        "wrong_aud": _forge(sub=alice, aud="other"),
        "wrong_iss": _forge(sub=alice, iss="evil"),
        "refresh": _forge(sub=alice, token_type="refresh"),
        "bad_sig": jwt.encode({"sub": alice}, "x" * 40, algorithm="HS256"),
        "alg_none": jwt.encode({"sub": alice, "token_type": "access"}, None, algorithm="none"),
        "garbage": "not.a.jwt",
        "unknown_user": _forge(),
    }
    response = await client.get(f"{API}/auth/me",
                                headers={"Authorization": f"Bearer {tokens[case]}"})
    assert response.status_code == 401


async def test_sec_04_inactive_user_rejected(env, client):
    """TC-SEC-04: a valid token for a deactivated account -> 401."""
    env.alice.is_active = False
    response = await client.get(f"{API}/auth/me", headers=env.headers(env.alice))
    assert response.status_code == 401


async def test_sec_05_login_success_and_failure(env, client):
    """TC-SEC-05: login returns a no-store bearer token; wrong password and
    unknown email give the same 401 (no user enumeration on login)."""
    ok = await client.post(f"{API}/auth/login", data={
        "grant_type": "password", "username": "ALICE@example.com",
        "password": "correct-horse-battery"})
    assert ok.status_code == 200 and ok.headers["Cache-Control"] == "no-store"
    me = await client.get(f"{API}/auth/me",
                          headers={"Authorization": f"Bearer {ok.json()['access_token']}"})
    assert me.json()["data"]["email"] == "alice@example.com"

    wrong = await client.post(f"{API}/auth/login", data={
        "grant_type": "password", "username": "alice@example.com", "password": "nope"})
    unknown = await client.post(f"{API}/auth/login", data={
        "grant_type": "password", "username": "ghost@example.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_sec_06_register_validation(env, client):
    """TC-SEC-06: weak password / bad email / extra fields -> 422; duplicate -> 409."""
    for body in ({"email": "x@example.com", "password": "short"},
                 {"email": "not-an-email", "password": "long-enough-pass"},
                 {"email": "y@example.com", "password": "long-enough-pass", "is_admin": True}):
        assert (await client.post(f"{API}/auth/register", json=body)).status_code == 422
    dup = await client.post(f"{API}/auth/register",
                            json={"email": "Alice@Example.com", "password": "long-enough-pass"})
    assert dup.status_code == 409


async def test_sec_07_login_failures_are_throttled(env, client):
    """TC-SEC-07 (BUG-018 fixed): after N failed logins for one e-mail the
    next attempts get 429 + Retry-After – even with the right password – so
    brute force (and the Argon2 CPU cost per attempt) is bounded."""
    from app.api import rate_limit_dependencies as limits

    max_failures = limits.get_login_email_failure_limiter().limit
    codes = []
    for _ in range(max_failures + 3):
        response = await client.post(f"{API}/auth/login", data={
            "grant_type": "password", "username": "alice@example.com", "password": "guess"})
        codes.append(response.status_code)
    assert codes[:max_failures] == [401] * max_failures
    assert set(codes[max_failures:]) == {429}
    locked = await client.post(f"{API}/auth/login", data={
        "grant_type": "password", "username": "ALICE@example.com",
        "password": "correct-horse-battery"})
    assert locked.status_code == 429 and int(locked.headers["Retry-After"]) >= 1
    # Another account from the same client is not locked by Alice's counter.
    bob = await client.post(f"{API}/auth/login", data={
        "grant_type": "password", "username": "bob@example.com",
        "password": "correct-horse-battery"})
    assert bob.status_code == 200


async def test_sec_07b_successful_login_resets_failures(env, client):
    """TC-SEC-07b: a successful login clears the e-mail failure counter."""
    from app.api import rate_limit_dependencies as limits

    max_failures = limits.get_login_email_failure_limiter().limit
    login = {"grant_type": "password", "username": "alice@example.com"}
    for _ in range(max_failures - 1):
        await client.post(f"{API}/auth/login", data={**login, "password": "guess"})
    ok = await client.post(f"{API}/auth/login",
                           data={**login, "password": "correct-horse-battery"})
    assert ok.status_code == 200
    again = await client.post(f"{API}/auth/login", data={**login, "password": "guess"})
    assert again.status_code == 401


async def test_sec_07c_ip_failure_limit_blocks_credential_spraying(env, client):
    """TC-SEC-07c: spraying one password over many e-mails from one client is
    capped by the per-IP failure counter."""
    from app.api import rate_limit_dependencies as limits

    ip_limit = limits.get_login_ip_failure_limiter().limit
    codes = []
    for index in range(ip_limit + 1):
        response = await client.post(f"{API}/auth/login", data={
            "grant_type": "password", "username": f"victim{index}@example.com",
            "password": "guess"})
        codes.append(response.status_code)
    assert codes[:ip_limit] == [401] * ip_limit
    assert codes[-1] == 429


async def test_sec_06b_register_is_rate_limited_per_ip(env, client):
    """TC-SEC-06b (BUG-033 mitigation): registration attempts per client IP
    are capped, so the duplicate-email response cannot be used to enumerate
    accounts at scale."""
    from app.api import rate_limit_dependencies as limits

    limit = limits.get_register_rate_limiter().limit
    codes = []
    for index in range(limit + 2):
        response = await client.post(f"{API}/auth/register", json={
            "email": f"user{index}@example.com", "password": "long-enough-pass"})
        codes.append(response.status_code)
    assert codes[:limit] == [201] * limit
    assert set(codes[limit:]) == {429}


# --------------------------------------------------------------------------
# Conversation API: validation, authorization, idempotency
# --------------------------------------------------------------------------
@pytest.mark.parametrize("body", [
    {"message": ""}, {"message": "   "}, {"message": "x" * 2001},
    {"message": "hi", "thread_id": "not-a-uuid"}, {"message": "hi", "cv_id": "x" * 101},
    {"message": "hi", "job_description": "x" * 20_001}, {},
])
async def test_api_04_conversation_request_validation(env, client, body):
    """TC-API-04: invalid conversation payloads -> 422 with field locations only."""
    response = await client.post(f"{API}/conversation/messages", json=body,
                                 headers=env.headers(env.alice))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "REQUEST_VALIDATION_ERROR"
    assert all(set(item) == {"type", "loc"} for item in error["details"]["errors"])


async def test_api_05_conversation_happy_path_and_replay(env, client):
    """TC-API-05: message processed once; same turn_id replays the stored reply."""
    env.harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    body = {"thread_id": str(uuid4()), "turn_id": str(uuid4()), "message": "Xin chào"}
    first = await client.post(f"{API}/conversation/messages", json=body,
                              headers=env.headers(env.alice))
    replay = await client.post(f"{API}/conversation/messages", json=body,
                               headers=env.headers(env.alice))
    assert first.status_code == replay.status_code == 200
    assert first.json()["data"] == replay.json()["data"]
    assert len(env.harness.analyzer.calls) == 1  # graph executed only once

    reused = await client.post(f"{API}/conversation/messages",
                               json={**body, "message": "khác"}, headers=env.headers(env.alice))
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "TURN_ID_REUSED"


async def test_api_05b_turn_lease_heartbeat_runs_only_while_processing(env):
    """TC-API-05b (BUG-029): while a long turn runs its lease is renewed by a
    heartbeat; the heartbeat stops once the turn completes."""
    import asyncio

    env.harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    original = env.harness.service.process

    async def slow_process(request):
        await asyncio.sleep(0.12)
        return await original(request)

    env.harness.service.process = slow_process
    service = AuthorizedConversationService(
        user_id=env.alice.user_id, service=env.harness.service, graph=env.harness.graph,
        ownership=env.ownership, turns=env.turns)
    service._heartbeat_seconds = 0.03
    from app.schemas.conversations_intent import ConversationRequest

    request = ConversationRequest(thread_id=uuid4(), turn_id=uuid4(), message="Xin chào")
    await service.process(request)
    turn = env.turns.turns[request.turn_id]
    assert turn["status"] == "completed"
    renewals = turn.get("renewals", 0)
    assert renewals >= 2
    await asyncio.sleep(0.1)
    assert turn.get("renewals", 0) == renewals  # no renewal after completion


async def test_api_06_thread_isolation_between_users(env, client):
    """TC-API-06: Bob cannot read, post to, resume or delete Alice's thread."""
    env.harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    thread_id = str(uuid4())
    await client.post(f"{API}/conversation/messages", headers=env.headers(env.alice),
                      json={"thread_id": thread_id, "message": "Xin chào"})
    bob = env.headers(env.bob)
    checks = [
        await client.get(f"{API}/conversation/threads/{thread_id}/messages", headers=bob),
        await client.post(f"{API}/conversation/messages", headers=bob,
                          json={"thread_id": thread_id, "message": "Xin chào"}),
        await client.post(f"{API}/conversation/resume", headers=bob, json={
            "thread_id": thread_id,
            "decision": {"review_id": "review_" + "a" * 16, "action": "approve"}}),
        await client.delete(f"{API}/conversation/threads/{thread_id}", headers=bob),
    ]
    assert [c.status_code for c in checks] == [404, 404, 404, 404]
    threads = await client.get(f"{API}/conversation/threads", headers=bob)
    assert threads.json()["data"] == []


async def test_api_07_cannot_attach_someone_elses_cv(env, client):
    """TC-API-07: posting another user's cv_id -> 404 (no existence oracle)."""
    cv_id = env.harness.add_cv()
    env.ownership.cvs[cv_id] = env.bob.user_id
    response = await client.post(f"{API}/conversation/messages", headers=env.headers(env.alice),
                                 json={"message": "Phân tích CV", "cv_id": cv_id})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_api_08_resume_validation(env, client):
    """TC-API-08: malformed resume decisions -> 422."""
    for decision in ({"review_id": "bad", "action": "approve"},
                     {"review_id": "review_" + "a" * 16, "action": "maybe"},
                     {"review_id": "review_" + "a" * 16, "action": "approve",
                      "input_overrides": {"system_prompt": "x"}}):
        response = await client.post(f"{API}/conversation/resume", headers=env.headers(env.alice),
                                     json={"thread_id": str(uuid4()), "decision": decision})
        assert response.status_code == 422


async def test_api_09_unhandled_error_is_generic(env, client):
    """TC-API-09: an unexpected exception -> 500 without stack trace/internal text."""
    async def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    env.search.search = boom
    response = await client.post(f"{API}/jobs/search", json={"query": "python"},
                                 headers=env.headers(env.alice))
    assert response.status_code == 500
    body = response.text
    assert "secret internal detail" not in body and "Traceback" not in body
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


async def test_api_10_job_search_validation(env, client):
    """TC-API-10: /jobs/search request validation (salary, paging, extra fields)."""
    bad = [{"query": ""}, {"query": "a", "page_size": 100},
           {"query": "a", "filters": {"salary_min": 10}}, {"query": "a", "unknown": 1}]
    for body in bad:
        response = await client.post(f"{API}/jobs/search", json=body,
                                     headers=env.headers(env.alice))
        assert response.status_code == 422


async def test_api_11_sql_injection_payload_is_inert(env, client):
    """TC-API-11: SQL meta-characters are passed as data to the search service."""
    payload = "python'; DROP TABLE jobs; --"
    response = await client.post(f"{API}/jobs/search", json={"query": payload},
                                 headers=env.headers(env.alice))
    assert response.status_code == 200
    assert env.search.requests[-1][0].query == payload


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
async def test_sec_08_cors_allows_only_configured_origin(client):
    """TC-SEC-08: allowed origin echoed; foreign origin not allowed."""
    allowed = await client.options("/health", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    foreign = await client.options("/health", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in foreign.headers


async def test_sec_09_500_responses_keep_cors_headers(env, client):
    """TC-SEC-09 (BUG-019 fixed): unhandled 500s are converted inside
    CORSMiddleware, so the browser can read the generic JSON error; a foreign
    origin still gets no CORS grant."""
    async def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    env.search.search = boom
    headers = {**env.headers(env.alice), "Origin": "http://localhost:5173"}
    response = await client.post(f"{API}/jobs/search", json={"query": "python"},
                                 headers=headers)
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "secret internal detail" not in response.text
    assert response.headers["X-Request-ID"]
    foreign = await client.post(f"{API}/jobs/search", json={"query": "python"},
                                headers={**env.headers(env.alice),
                                         "Origin": "https://evil.example"})
    assert foreign.status_code == 500
    assert "access-control-allow-origin" not in foreign.headers


def test_sec_10_short_jwt_secret_rejected():
    """TC-SEC-10: AUTH_JWT_SECRET shorter than 32 bytes is refused at startup."""
    from pydantic import ValidationError

    from app.core.auth_config import AuthSettings

    with pytest.raises(ValidationError):
        AuthSettings(auth_jwt_secret="short")


def test_sec_11_wildcard_cors_rejected():
    """TC-SEC-11: '*' CORS origin is refused (credentials are allowed)."""
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(backend_cors_origins=["*"])


async def test_sec_12_token_lifetime(env):
    """TC-SEC-12: access token expires after the configured minutes."""
    settings = get_auth_settings()
    token = create_access_token(UUID(int=1), settings)
    claims = jwt.decode(token, options={"verify_signature": False})
    lifetime = timedelta(seconds=claims["exp"] - claims["iat"])
    assert lifetime == timedelta(minutes=settings.auth_access_token_minutes)
