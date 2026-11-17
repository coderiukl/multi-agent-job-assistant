"""Read-only smoke tests against an already running local stack.

Enabled only when LIVE_BACKEND_URL is set, e.g.:
    LIVE_BACKEND_URL=http://127.0.0.1:8001 LIVE_QDRANT_URL=http://127.0.0.1:6333 \
        pytest tests/live -m live

They never authenticate, never send a valid search (so no LLM/embedding
cost) and never write data: only health, OpenAPI, 401/422 paths and Qdrant
collection metadata are read.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.live

BACKEND = os.environ.get("LIVE_BACKEND_URL")
QDRANT = os.environ.get("LIVE_QDRANT_URL")
COLLECTION = os.environ.get("LIVE_QDRANT_COLLECTION", "jobs_bge_m3_v2")


@pytest.fixture
def backend():
    if not BACKEND:
        pytest.skip("LIVE_BACKEND_URL not set")
    with httpx.Client(base_url=BACKEND, timeout=10) as client:
        yield client


def test_live_01_health(backend):
    """TC-LIVE-01: /health is 200 and healthy."""
    response = backend.get("/health")
    assert response.status_code == 200 and response.json()["data"]["status"] == "healthy"


def test_live_02_openapi_security_map(backend):
    """TC-LIVE-02: every business endpoint declares bearer security – only
    health, register and login are public (BUG-001 fixed)."""
    spec = backend.get("/openapi.json").json()
    unauthenticated = {
        f"{method.upper()} {path}"
        for path, operations in spec["paths"].items()
        for method, operation in operations.items()
        if not operation.get("security")
    }
    assert unauthenticated == {
        "GET /health", "POST /api/v1/auth/register", "POST /api/v1/auth/login",
    }


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/api/v1/conversation/threads"),
    ("POST", "/api/v1/conversation/messages"),
    ("GET", "/api/v1/auth/me"),
])
def test_live_03_protected_endpoints_401(backend, method, path):
    """TC-LIVE-03: protected endpoints reject anonymous calls."""
    assert backend.request(method, path, json={"message": "x"}).status_code == 401


def test_live_04_anonymous_job_search_rejected(backend):
    """TC-LIVE-04 (BUG-001 fixed): an anonymous (deliberately invalid) search
    is rejected with 401 before any validation or paid work."""
    response = backend.post("/api/v1/jobs/search",
                            json={"query": "python", "filters": {"salary_min": 1}})
    assert response.status_code == 401


def test_live_05_cors_rejects_foreign_origin(backend):
    """TC-LIVE-05: preflight from an unknown origin is refused."""
    response = backend.options("/api/v1/jobs/search", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 400


def test_live_06_qdrant_collection_shape():
    """TC-LIVE-06: collection exists, 1024-d cosine, payload indexes present."""
    if not QDRANT:
        pytest.skip("LIVE_QDRANT_URL not set")
    info = httpx.get(f"{QDRANT}/collections/{COLLECTION}", timeout=10).json()["result"]
    vectors = info["config"]["params"]["vectors"]
    assert (vectors["size"], vectors["distance"]) == (1024, "Cosine")
    assert info["points_count"] > 0
    assert {"location_keys", "seniority_level", "expires_at", "skill_keys"} <= set(
        info["payload_schema"])
