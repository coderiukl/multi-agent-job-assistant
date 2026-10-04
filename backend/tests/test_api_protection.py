from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth_dependencies import get_auth_service, get_auth_settings, get_current_user
from app.api.resource_dependencies import get_authorized_conversation_service, get_authorized_cv_processing_service
from app.api.v1.endpoints import conversation, cvs
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import ResourceNotFoundException
from app.core.security import create_access_token
from app.services.auth import AuthService
from app.services.authorized_conversation import AuthorizedConversationService


@pytest.fixture
def api(user, user_repository, auth_settings):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(conversation.router, prefix="/api/v1/conversation")
    app.include_router(cvs.router, prefix="/api/v1/cvs")
    service = AuthService(user_repository, auth_settings)
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_auth_settings] = lambda: auth_settings
    downstream = SimpleNamespace(**{name: AsyncMock() for name in [
        "process", "get_history", "delete_history", "resume", "analyze_intent",
    ]})
    foreign_thread = uuid4()
    ownership = SimpleNamespace(
        get_thread_owner=AsyncMock(return_value=uuid4()),
        require_thread=AsyncMock(side_effect=ResourceNotFoundException(
            resource="Conversation", identifier=str(foreign_thread)
        )),
    )
    def authorized(current_user=Depends(get_current_user)):
        return AuthorizedConversationService(
            user_id=current_user.user_id, service=downstream,
            graph=SimpleNamespace(aget_state=AsyncMock()), ownership=ownership,
        )
    def cv_service(current_user=Depends(get_current_user)):
        return SimpleNamespace(process=AsyncMock())
    app.dependency_overrides[get_authorized_conversation_service] = authorized
    app.dependency_overrides[get_authorized_cv_processing_service] = cv_service
    with TestClient(app) as client:
        yield client, downstream, foreign_thread, create_access_token(user.user_id, auth_settings)


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/v1/conversation/threads", None),
    ("post", "/api/v1/conversation/messages", {"message": "Hello"}),
    ("post", "/api/v1/conversation/intent-analysis", {"message": "Hello"}),
    ("post", "/api/v1/conversation/resume", {"thread_id": str(uuid4()), "decision": {"action": "approve"}}),
    ("post", "/api/v1/cvs", None),
])
def test_protected_routes_reject_anonymous(api, method, path, body):
    client, _, _, _ = api
    kwargs = {"json": body} if body is not None else {}
    if path.endswith("/cvs"):
        kwargs["files"] = {"file": ("cv.pdf", b"%PDF-test", "application/pdf")}
    assert client.request(method, path, **kwargs).status_code == 401


@pytest.mark.parametrize("operation", ["read", "delete", "send", "resume"])
def test_foreign_thread_returns_404_before_processing(api, operation):
    client, downstream, thread, token = api
    headers = {"Authorization": f"Bearer {token}"}
    if operation == "read":
        response = client.get(f"/api/v1/conversation/threads/{thread}/messages", headers=headers)
    elif operation == "delete":
        response = client.delete(f"/api/v1/conversation/threads/{thread}", headers=headers)
    elif operation == "send":
        response = client.post("/api/v1/conversation/messages", headers=headers, json={"thread_id": str(thread), "message": "Hello"})
    else:
        response = client.post("/api/v1/conversation/resume", headers=headers, json={"thread_id": str(thread), "decision": {"action": "approve"}})
    assert response.status_code == 404
    for method in ["get_history", "delete_history", "process", "resume"]:
        getattr(downstream, method).assert_not_awaited()
