"""Shared test fixtures for the Multi-Agent Job Assistant backend.

Safety rules enforced here (see TEST_PLAN.md):
* Environment variables are overridden *before* any ``app`` import so the
  real ``backend/.env`` can never route tests to the real PostgreSQL, Qdrant
  or paid LLM endpoints. Every external URL points at a closed local port.
* LLM, embedding, vector and repository dependencies are replaced by
  deterministic in-memory fakes.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Environment isolation (must run before importing ``app``)
# --------------------------------------------------------------------------
_SAFE_ENV = {
    "ENVIRONMENT": "testing",
    "APP_DEBUG": "false",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "console",
    "LLM_PROVIDER": "9router",
    "LLM_MODEL": "test-model",
    "NINE_ROUTER_API_KEY": "test-key-not-real",
    # Port 9 (discard) on loopback: any accidental LLM call fails fast.
    "NINE_ROUTER_BASE_URL": "http://127.0.0.1:9/v1",
    "OPENAI_API_KEY": "",
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_TRACING_V2": "false",
    "LANGSMITH_API_KEY": "",
    "QDRANT_URL": "http://127.0.0.1:9",
    "JOB_STORAGE_BACKEND": "postgres",
    "JOB_DATABASE_URL": os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://nobody:nobody@127.0.0.1:9/not_a_database",
    ),
    "CONVERSATION_MEMORY_BACKEND": "memory",
    "AUTH_JWT_SECRET": "test-secret-for-unit-tests-only-0123456789abcdef",
    "AUTH_JWT_ISSUER": "multi-agent-job-assistant",
    "AUTH_JWT_AUDIENCE": "job-assistant-api",
    "BACKEND_CORS_ORIGINS": '["http://localhost:5173"]',
}
os.environ.update(_SAFE_ENV)

import hashlib  # noqa: E402
import tempfile  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

_TMP_STORAGE = Path(tempfile.mkdtemp(prefix="jobassist-tests-"))
os.environ["STORAGE_DIR"] = str(_TMP_STORAGE)
os.environ["UPLOAD_DIR"] = str(_TMP_STORAGE / "uploads")
os.environ["EMBEDDING_CACHE_DIR"] = str(_TMP_STORAGE / "models")

import pytest  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.exceptions import AppException, ResourceNotFoundException  # noqa: E402
from app.normalizers.job import JobNormalizer  # noqa: E402
from app.schemas.career_advice import CareerAdviceResult  # noqa: E402
from app.schemas.conversation_search_context import SearchContextPatch  # noqa: E402
from app.schemas.conversations_intent import (  # noqa: E402
    ConversationIntent,
    IntentAnalysisResult,
)
from app.schemas.cover_letter import CoverLetterResult  # noqa: E402
from app.schemas.cv_analysis import (  # noqa: E402
    CVAnalysisBreakdown,
    CVAnalysisResult,
    CVQualityLevel,
)
from app.schemas.cv_profile import (  # noqa: E402
    CVProfile,
    Education,
    Language,
    PersonalInformation,
    Project,
    WorkExperience,
)
from app.schemas.job import JobCandidate, NormalizedJob, SeniorityLevel  # noqa: E402
from app.schemas.job_matching import (  # noqa: E402
    JobMatchingBreakDown,
    JobMatchingResult,
    MatchRecommendation,
)
from app.schemas.job_search import (  # noqa: E402
    JobSearchHit,
    JobSearchResult,
    JobSearchScore,
    JobSearchStrategy,
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: read-only smoke tests against an already running local stack "
        "(requires LIVE_BACKEND_URL).",
    )
    config.addinivalue_line(
        "markers",
        "known_bug(id): test documents a confirmed defect listed in BUG_REPORT.md",
    )


# --------------------------------------------------------------------------
# Domain factories
# --------------------------------------------------------------------------
def make_cv_profile(**overrides: Any) -> CVProfile:
    data: dict[str, Any] = {
        "personal_information": PersonalInformation(
            full_name="Nguyen Van Test",
            email="candidate@example.com",
            phone="+84 900 000 000",
            location="Ho Chi Minh",
            linkedin_url=None,
            github_url="https://github.com/example",
            portfolio_url=None,
        ),
        "professional_summary": "Backend developer focused on Python APIs.",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "work_experiences": [
            WorkExperience(
                job_title="Backend Developer",
                company="Example Co",
                location="Ho Chi Minh",
                start_date="01/2022",
                end_date="01/2024",
                is_current=False,
                responsibilities=["Built REST APIs with FastAPI"],
                achievements=["Reduced latency by 30%"],
            )
        ],
        "educations": [
            Education(
                institution="HCMUS",
                degree="Bachelor",
                field_of_study="Computer Science",
                start_date="2018",
                end_date="2022",
                description=None,
            )
        ],
        "projects": [
            Project(
                name="Job Crawler",
                description="Async crawler",
                technologies=["Python", "Airflow"],
                url=None,
            )
        ],
        "certifications": [],
        "languages": [Language(name="English", proficiency="IELTS 6.5")],
    }
    data.update(overrides)
    return CVProfile(**data)


def make_job(
    index: int = 0,
    *,
    title: str = "Python Backend Intern",
    company: str = "Acme",
    description: str = "Build APIs with Python and FastAPI.",
    skills: list[str] | None = None,
    location: str | None = "Ho Chi Minh",
    seniority: SeniorityLevel = SeniorityLevel.INTERN,
    source: str = "test",
    posted_days_ago: float | None = 1,
    **extra: Any,
) -> NormalizedJob:
    posted_at = (
        datetime.now(UTC) - timedelta(days=posted_days_ago)
        if posted_days_ago is not None
        else None
    )
    candidate = JobCandidate(
        title=title,
        company=company,
        description=description,
        location=location,
        seniority_level=seniority,
        skills=skills if skills is not None else ["Python", "FastAPI"],
        source=source,
        source_job_id=f"job-{index}",
        source_url=f"https://jobs.example.com/{source}/{index}",
        posted_at=posted_at,
        **extra,
    )
    return JobNormalizer().normalize(candidate)


def make_hit(job: NormalizedJob, final: float = 0.8) -> JobSearchHit:
    return JobSearchHit(
        job=job,
        score=JobSearchScore(semantic=final, keyword=0.5, filter_match=1.0,
                             freshness=1.0, final=final),
        matched_terms=["Python"],
        reasons=["test"],
    )


def make_search_result(jobs: list[NormalizedJob], query: str = "python") -> JobSearchResult:
    return JobSearchResult(
        query=query,
        strategy=JobSearchStrategy.HYBRID,
        total=len(jobs),
        page=1,
        page_size=10,
        retrieved_count=len(jobs),
        has_more=False,
        items=[make_hit(job) for job in jobs],
    )


def make_match_result(score: float = 75.0, job_id: str | None = None) -> JobMatchingResult:
    if score >= 85:
        recommendation = MatchRecommendation.STRONG_MATCH
    elif score >= 70:
        recommendation = MatchRecommendation.GOOD_MATCH
    elif score >= 50:
        recommendation = MatchRecommendation.PARTIAL_MATCH
    else:
        recommendation = MatchRecommendation.LOW_MATCH
    return JobMatchingResult(
        breakdown=JobMatchingBreakDown(
            technical_skills=0, experience=0, education=0, projects=0,
            language_and_certifications=0,
        ),
        strengths=["Python"],
        gaps=["Kubernetes"],
        evidence=[],
        summary=f"Fake match {score}",
        confidence=0.8,
        job_id=job_id,
        overall_score=score,
        recommendation=recommendation,
        model_confidence=0.8,
    )


def intent(
    primary: ConversationIntent,
    *secondary: ConversationIntent,
    patch: dict[str, Any] | None = None,
    clarification: str | None = None,
) -> IntentAnalysisResult:
    return IntentAnalysisResult(
        primary_intent=primary,
        secondary_intents=list(secondary),
        confidence=0.9,
        search_context_patch=SearchContextPatch(**(patch or {})),
        needs_clarification=clarification is not None,
        clarification_question=clarification,
    )


# --------------------------------------------------------------------------
# Fake collaborators for the LangGraph conversation graph
# --------------------------------------------------------------------------
class FakeAnalyzer:
    """Deterministic stand-in for the LLM intent analyzer."""

    def __init__(self) -> None:
        self.rules: list[tuple[str, IntentAnalysisResult]] = []
        self.default = intent(ConversationIntent.SMALL_TALK)
        self.calls: list[Any] = []

    def on(self, substring: str, result: IntentAnalysisResult) -> FakeAnalyzer:
        self.rules.append((substring.casefold(), result))
        return self

    async def analyze(self, input_data: Any) -> IntentAnalysisResult:
        self.calls.append(input_data)
        message = input_data.message.casefold()
        for substring, result in self.rules:
            if substring in message:
                return result
        return self.default


class FakeCVRepository:
    def __init__(self) -> None:
        self.profiles: dict[str, CVProfile] = {}

    async def get(self, cv_id: str) -> CVProfile | None:
        return self.profiles.get(cv_id)

    async def save(self, cv_id: str, profile: CVProfile) -> None:
        self.profiles[cv_id] = profile

    async def delete(self, cv_id: str) -> None:
        self.profiles.pop(cv_id, None)


class FakeCVAnalysisService:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    async def analyze(self, analysis_input: Any) -> CVAnalysisResult:
        self.inputs.append(analysis_input)
        return CVAnalysisResult(
            breakdown=CVAnalysisBreakdown(
                completeness=80, professional_summary=70, skills=80,
                work_experience=75, projects=70, education_and_credentials=80,
            ),
            summary="CV khá tốt.",
            confidence=0.8,
            overall_score=76.0,
            quality_level=CVQualityLevel.GOOD,
        )


class FakeCareerAdviceService:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    async def advise(self, advice_input: Any) -> CareerAdviceResult:
        self.inputs.append(advice_input)
        return CareerAdviceResult(
            career_goal="Backend Developer",
            summary="Học thêm Docker và Kubernetes.",
            confidence=0.7,
            is_personalized=advice_input.cv_profile is not None,
            model_confidence=0.7,
        )


class FakeCoverLetterService:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    async def generate(self, letter_input: Any) -> CoverLetterResult:
        self.inputs.append(letter_input)
        body = f"Tôi muốn ứng tuyển vị trí {letter_input.job.title or 'này'}."
        return CoverLetterResult(
            language="vi",
            tone="professional",
            subject="Ứng tuyển",
            salutation="Kính gửi",
            opening_paragraph="Xin chào.",
            body_paragraphs=[body],
            closing_paragraph="Cảm ơn.",
            complimentary_close="Trân trọng",
            signature_name="Nguyen Van Test",
            confidence=0.8,
            full_text=f"Xin chào. {body} Cảm ơn.",
            word_count=10,
        )


class FakeJobSearchService:
    def __init__(self, jobs: list[NormalizedJob] | None = None) -> None:
        self.jobs = jobs if jobs is not None else [make_job(i) for i in range(3)]
        self.requests: list[Any] = []

    async def search(self, request: Any, *, context: Any = None) -> JobSearchResult:
        self.requests.append((request, context))
        return make_search_result(self.jobs, query=request.query)


class FakeJobMatchingService:
    def __init__(self) -> None:
        self.inputs: list[Any] = []
        self.scores: dict[str | None, float] = {}
        self.failures: set[str | None] = set()
        self.delay_for: dict[str | None, float] = {}

    async def match(self, matching_input: Any) -> JobMatchingResult:
        import asyncio

        self.inputs.append(matching_input)
        job_id = matching_input.job.job_id
        if job_id in self.delay_for:
            await asyncio.sleep(self.delay_for[job_id])
        if job_id in self.failures:
            raise AppException(status_code=502, code="INVALID_STRUCTURED_OUTPUT",
                               message="fake failure")
        return make_match_result(self.scores.get(job_id, 72.0), job_id=job_id)


class GraphHarness:
    """Builds the real graph + ConversationService around fake agents."""

    def __init__(self, *, workflow_timeout: float = 5.0) -> None:
        from langgraph.checkpoint.memory import InMemorySaver

        from app.graphs.conversation import ConversationNodes, build_conversation_graph
        from app.services.conversation import ConversationService

        self.analyzer = FakeAnalyzer()
        self.cv_repository = FakeCVRepository()
        self.cv_analysis = FakeCVAnalysisService()
        self.career_advice = FakeCareerAdviceService()
        self.cover_letter = FakeCoverLetterService()
        self.job_search = FakeJobSearchService()
        self.job_matching = FakeJobMatchingService()
        self.checkpointer = InMemorySaver()
        nodes = ConversationNodes(
            analyzer=self.analyzer,
            cv_repository=self.cv_repository,
            cv_analysis_service=self.cv_analysis,
            career_advice_service=self.career_advice,
            cover_letter_service=self.cover_letter,
            job_search_service=self.job_search,
            job_matching_service=self.job_matching,
            workflow_matching_timeout_seconds=workflow_timeout,
        )
        self.graph = build_conversation_graph(nodes, checkpointer=self.checkpointer)
        self.service = ConversationService(graph=self.graph)
        self.thread_id = uuid4()

    def add_cv(self, cv_id: str | None = None, profile: CVProfile | None = None) -> str:
        cv_id = cv_id or uuid4().hex
        self.cv_repository.profiles[cv_id] = profile or make_cv_profile()
        return cv_id

    async def send(self, message: str, **fields: Any):
        from app.schemas.conversations_intent import ConversationRequest

        request = ConversationRequest(thread_id=self.thread_id, message=message, **fields)
        return await self.service.process(request)

    async def resume(self, review_id: str, action: str = "approve", **decision: Any):
        from app.schemas.human_review import ResumeConversationRequest

        request = ResumeConversationRequest(
            thread_id=self.thread_id,
            decision={"review_id": review_id, "action": action, **decision},
        )
        return await self.service.resume(request)

    async def state(self) -> dict[str, Any]:
        snapshot = await self.graph.aget_state(
            {"configurable": {"thread_id": str(self.thread_id)}}
        )
        return dict(snapshot.values)


@pytest.fixture
def harness() -> GraphHarness:
    return GraphHarness()


# --------------------------------------------------------------------------
# In-memory replacements for PostgreSQL-backed authorization repositories
# --------------------------------------------------------------------------
class InMemoryOwnership:
    def __init__(self) -> None:
        self.cvs: dict[str, UUID] = {}
        self.threads: dict[UUID, tuple[UUID, datetime]] = {}

    async def require_cv(self, *, cv_id: str, user_id: UUID) -> None:
        if self.cvs.get(cv_id) != user_id:
            raise ResourceNotFoundException(resource="CV", identifier=cv_id)

    async def get_thread_owner(self, thread_id: UUID) -> UUID | None:
        owner = self.threads.get(thread_id)
        return owner[0] if owner else None

    async def require_thread(self, *, thread_id: UUID, user_id: UUID) -> None:
        if await self.get_thread_owner(thread_id) != user_id:
            raise ResourceNotFoundException(resource="Conversation",
                                            identifier=str(thread_id))

    async def claim_thread(self, *, thread_id: UUID, user_id: UUID) -> None:
        self.threads.setdefault(thread_id, (user_id, datetime.now(UTC)))
        if self.threads[thread_id][0] != user_id:
            raise ResourceNotFoundException(resource="Conversation",
                                            identifier=str(thread_id))

    async def list_threads_for_user(self, user_id: UUID):
        return [(t, c) for t, (u, c) in self.threads.items() if u == user_id]


class InMemoryTurns:
    def __init__(self) -> None:
        self.turns: dict[UUID, dict[str, Any]] = {}

    async def begin(self, *, turn_id, thread_id, user_id, operation, payload_hash):
        from app.repositories.conversation_turn import TurnAcquisition

        existing = self.turns.get(turn_id)
        if existing is not None:
            same = (existing["thread_id"], existing["user_id"], existing["operation"],
                    existing["payload_hash"]) == (thread_id, user_id, operation, payload_hash)
            if not same:
                raise AppException(status_code=409, code="TURN_ID_REUSED", message="reused")
            if existing["status"] == "completed":
                return TurnAcquisition(replay_response=existing["response"])
            raise AppException(status_code=409, code="CONVERSATION_TURN_IN_PROGRESS",
                               message="busy")
        if any(t["thread_id"] == thread_id and t["status"] == "processing"
               for t in self.turns.values()):
            raise AppException(status_code=409, code="CONVERSATION_TURN_IN_PROGRESS",
                               message="busy")
        self.turns[turn_id] = {"thread_id": thread_id, "user_id": user_id,
                               "operation": operation, "payload_hash": payload_hash,
                               "status": "processing", "response": None}
        return TurnAcquisition()

    async def renew_lease(self, *, turn_id):
        turn = self.turns.get(turn_id)
        if turn is None or turn["status"] != "processing":
            return False
        turn["renewals"] = turn.get("renewals", 0) + 1
        return True

    async def complete(self, *, turn_id, response_data):
        self.turns[turn_id].update(status="completed", response=response_data)

    async def fail(self, *, turn_id, error_code):
        self.turns[turn_id].update(status="failed", error=error_code)

    async def delete_for_thread(self, thread_id):
        for key in [k for k, v in self.turns.items() if v["thread_id"] == thread_id]:
            del self.turns[key]


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
