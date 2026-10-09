from pydantic import ValidationError

from app.schemas.cv_profile import CVProfile, PersonalInformation
from app.schemas.job_matching import (
    JobMatchingAssessment,
    JobMatchingBreakDown,
    JobMatchingInput,
    JobMatchTarget,
    MatchDimension,
    MatchEvidence,
    MatchStatus,
)
from app.services.job_matching import JobMatchingService
from app.services.job_matching_context import (
    build_cv_evidence_catalog,
    build_job_requirements,
)


def _profile(*, needs_review: bool = False) -> CVProfile:
    return CVProfile(
        personal_information=PersonalInformation(
            full_name="Candidate",
            email=None,
            phone=None,
            location=None,
            linkedin_url=None,
            github_url=None,
            portfolio_url=None,
        ),
        professional_summary=None,
        skills=["Python"],
        work_experiences=[],
        educations=[],
        projects=[],
        certifications=[],
        languages=[],
        needs_review=needs_review,
    )


class _FakeAgent:
    calls = 0

    async def assess(self, matching_input: JobMatchingInput) -> JobMatchingAssessment:
        self.calls += 1
        cv_evidence_id = matching_input.cv_evidence_catalog[0].cv_evidence_id
        evidence = [
            MatchEvidence(
                dimension=requirement.dimension,
                requirement_id=requirement.requirement_id,
                requirement=requirement.text,
                cv_evidence_ids=[cv_evidence_id],
                status=MatchStatus.MATCHED,
                explanation="Supported by normalized CV evidence.",
            )
            for requirement in matching_input.requirements
        ]
        applicable = {item.dimension for item in matching_input.requirements}

        return JobMatchingAssessment(
            breakdown=JobMatchingBreakDown(
                technical_skills=(
                    80 if MatchDimension.TECHNICAL_SKILLS in applicable else 0
                ),
                experience=(70 if MatchDimension.EXPERIENCE in applicable else 0),
                education=50 if MatchDimension.EDUCATION in applicable else 0,
                projects=60 if MatchDimension.PROJECTS in applicable else 0,
                language_and_certifications=(
                    60
                    if MatchDimension.LANGUAGES_AND_CERTIFICATIONS in applicable
                    else 0
                ),
            ),
            strengths=["Python"],
            gaps=[],
            evidence=evidence,
            summary="The score is grounded in normalized references.",
            confidence=0.95,
        )


def test_matched_evidence_requires_normalized_cv_reference() -> None:
    try:
        MatchEvidence(
            dimension=MatchDimension.TECHNICAL_SKILLS,
            requirement_id="req_0123456789abcdef",
            requirement="Python",
            cv_evidence_ids=[],
            status=MatchStatus.MATCHED,
            explanation="Matched.",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("matched evidence without CV IDs must be rejected")


def test_requirement_and_cv_evidence_ids_are_stable() -> None:
    job = JobMatchTarget(
        description="Python skill required. Bachelor degree preferred.",
        skills=["Python"],
    )
    profile = _profile()

    assert build_job_requirements(job) == build_job_requirements(job)
    assert build_cv_evidence_catalog(profile) == build_cv_evidence_catalog(profile)
    assert all(
        item.requirement_id.startswith("req_") for item in build_job_requirements(job)
    )
    assert all(
        item.cv_evidence_id.startswith("cv_")
        for item in build_cv_evidence_catalog(profile)
    )


async def test_service_uses_code_applicability_calibration_and_cache() -> None:
    agent = _FakeAgent()
    service = JobMatchingService(
        agent=agent,
        model_version="test-model",
        cache_size=10,
    )
    matching_input = JobMatchingInput(
        cv_profile=_profile(needs_review=True),
        job=JobMatchTarget(
            description="Python skill required. Bachelor degree preferred.",
            skills=["Python"],
        ),
    )

    first = await service.match(matching_input)
    second = await service.match(matching_input)

    assert agent.calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.model_confidence == 0.95
    assert first.confidence < first.model_confidence
    assert first.breakdown.experience == 0
    assert all(item.requirement_id for item in first.evidence)
    assert all(item.cv_evidence for item in first.evidence)
