import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

os.environ.update(
    ENVIRONMENT="testing",
    APP_DEBUG="false",
    LANGSMITH_TRACING="false",
    CONVERSATION_MEMORY_BACKEND="memory",
    AUTH_JWT_SECRET="test-only-secret-0123456789-abcdef-0123456789",
)

from app.core.auth_config import AuthSettings
from app.core.config import Settings
from app.schemas.cv_profile import CVProfile


@pytest.fixture(autouse=True)
def block_external_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not call external HTTP services")

    async def forbidden_async(*args, **kwargs):
        forbidden()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", forbidden_async
    )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        storage_dir=tmp_path,
        upload_dir=tmp_path / "uploads",
    )


@pytest.fixture
def auth_settings():
    return AuthSettings(_env_file=None)


@pytest.fixture
def user():
    return SimpleNamespace(
        user_id=uuid4(), email="alice@example.com", is_active=True,
        created_at=datetime.now(UTC), password_hash="",
    )


@pytest.fixture
def user_repository(user):
    return SimpleNamespace(
        get_by_email=AsyncMock(return_value=user),
        get_by_id=AsyncMock(return_value=user),
        create=AsyncMock(return_value=user),
    )


@pytest.fixture
def cv_profile():
    return CVProfile.model_validate({
        "personal_information": {
            "full_name": "Test Candidate", "email": "alice@example.com",
            "phone": None, "location": "Ho Chi Minh City",
            "linkedin_url": None, "github_url": None, "portfolio_url": None,
        },
        "professional_summary": "Python developer",
        "skills": ["Python", "SQL"], "work_experiences": [],
        "educations": [], "projects": [], "certifications": [], "languages": [],
    })


@pytest.fixture
def results():
    from app.schemas.career_advice import CareerAdviceResult
    from app.schemas.cover_letter import CoverLetterResult
    from app.schemas.cv_analysis import CVAnalysisResult
    from app.schemas.job_matching import JobMatchingResult
    from app.schemas.job_search import JobSearchResult

    return {
        "cv_analysis": CVAnalysisResult(
            breakdown={name: 70 for name in [
                "completeness", "professional_summary", "skills", "work_experience",
                "projects", "education_and_credentials",
            ]}, summary="Improve project evidence", confidence=0.8,
            overall_score=70, quality_level="good",
        ),
        "job_matching": JobMatchingResult(
            breakdown={name: 70 for name in [
                "technical_skills", "experience", "education", "projects",
                "language_and_certifications",
            ]}, summary="Relevant Python skills", confidence=0.8,
            overall_score=70, recommendation="good_match",
        ),
        "career_advice": CareerAdviceResult(
            career_goal="Python developer", summary="Build a project", confidence=0.8,
            is_personalized=True,
        ),
        "cover_letter": CoverLetterResult(
            language="en", tone="professional", subject="Application",
            salutation="Dear hiring team", opening_paragraph="I am applying.",
            body_paragraphs=["I have Python skills."], closing_paragraph="Thank you.",
            complimentary_close="Sincerely", full_text="Test letter", word_count=2,
            confidence=0.8,
        ),
        "job_search": JobSearchResult(
            query="Python", strategy="hybrid", total=0, page=1, page_size=10, items=[],
        ),
    }
