"""Job Matching Agent / Service tests (Phase 2C).

The LLM is replaced by a scripted agent that returns a schema-valid
JobMatchingAssessment built from the *real* requirement and CV-evidence
catalogs, so the deterministic post-processing (evidence resolution, years
check, mandatory gate, weighting, caching, concurrency) is tested for real.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.cv_profile import WorkExperience
from app.schemas.job_matching import (
    JobMatchingAssessment,
    JobMatchingInput,
    JobMatchTarget,
    MatchDimension,
    MatchRecommendation,
    MatchStatus,
)
from app.services.job_matching import JobMatchingService
from app.services.job_matching_context import (
    build_cv_evidence_catalog,
    build_job_requirements,
    calculate_total_experience_years,
)
from tests.conftest import make_cv_profile

FIELD = {
    MatchDimension.TECHNICAL_SKILLS: "technical_skills",
    MatchDimension.EXPERIENCE: "experience",
    MatchDimension.PROJECTS: "projects",
    MatchDimension.EDUCATION: "education",
    MatchDimension.LANGUAGES_AND_CERTIFICATIONS: "language_and_certifications",
}


class ScriptedAgent:
    """Marks every requirement with ``status`` and gives each applicable
    dimension ``score`` (0 when no supporting evidence exists)."""

    def __init__(self, status: MatchStatus = MatchStatus.MATCHED, score: float = 90.0,
                 per_requirement: dict[str, MatchStatus] | None = None,
                 delay: float = 0.0) -> None:
        self.status = status
        self.score = score
        self.per_requirement = per_requirement or {}
        self.delay = delay
        self.calls = 0

    async def assess(self, matching_input: JobMatchingInput) -> JobMatchingAssessment:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        evidence, supported = [], set()
        catalog = {item.dimension: item for item in matching_input.cv_evidence_catalog}
        any_evidence = matching_input.cv_evidence_catalog[0]
        for requirement in matching_input.requirements:
            status = self.status
            for needle, forced in self.per_requirement.items():
                if needle in requirement.text:
                    status = forced
            ids = []
            if status in {MatchStatus.MATCHED, MatchStatus.PARTIAL}:
                ids = [(catalog.get(requirement.dimension) or any_evidence).cv_evidence_id]
                supported.add(requirement.dimension)
            evidence.append({
                "dimension": requirement.dimension.value,
                "requirement_id": requirement.requirement_id,
                "requirement": requirement.text,
                "cv_evidence_ids": ids,
                "status": status.value,
                "explanation": "scripted",
            })
        breakdown = {f: (self.score if d in supported else 0.0) for d, f in FIELD.items()}
        return JobMatchingAssessment.model_validate({
            "breakdown": breakdown, "evidence": evidence, "summary": "scripted",
            "confidence": 0.9,
        })


def service(agent: ScriptedAgent, **kwargs) -> JobMatchingService:
    return JobMatchingService(agent=agent, model_version="test", **kwargs)


def matching_input(description: str, skills: list[str] | None = None, **cv) -> JobMatchingInput:
    return JobMatchingInput(
        cv_profile=make_cv_profile(**cv),
        job=JobMatchTarget(description=description, skills=skills or []),
    )


# --------------------------------------------------------------------------
# Requirement extraction from the JD
# --------------------------------------------------------------------------
def test_mat_01_skills_become_technical_requirements():
    """TC-MAT-01: structured job skills -> technical_skills requirements."""
    reqs = build_job_requirements(JobMatchTarget(description="x", skills=["Python", "Docker"]))
    assert [(r.dimension, r.text) for r in reqs] == [
        (MatchDimension.TECHNICAL_SKILLS, "Python"),
        (MatchDimension.TECHNICAL_SKILLS, "Docker"),
    ]


def test_mat_02_vietnamese_jd_is_classified():
    """TC-MAT-02: Vietnamese keyword lines are recognised (accents folded)."""
    jd = ("Tối thiểu 2 năm kinh nghiệm Python.\nTốt nghiệp đại học CNTT.\n"
          "Có chứng chỉ AWS.\nTừng tham gia dự án lớn.")
    dims = [r.dimension for r in build_job_requirements(JobMatchTarget(description=jd))]
    assert dims == [MatchDimension.EXPERIENCE, MatchDimension.EDUCATION,
                    MatchDimension.LANGUAGES_AND_CERTIFICATIONS, MatchDimension.PROJECTS]


async def test_mat_03_direct_jd_with_plain_skill_list_is_scored():
    """TC-MAT-03 (BUG-003 fixed): a pasted JD ('Yêu cầu: Python, FastAPI,
    Docker') must produce requirements; otherwise every CV scores 0 / low_match."""
    jd = "Backend Developer\nYêu cầu: Python, FastAPI, Docker, PostgreSQL"
    result = await service(ScriptedAgent()).match(matching_input(jd))
    assert result.overall_score > 0
    assert result.recommendation != MatchRecommendation.LOW_MATCH


@pytest.mark.parametrize(("jd", "expected"), [
    # header line without any dimension keyword
    ("Backend Developer\nYêu cầu: Python, FastAPI, Docker, PostgreSQL",
     [(MatchDimension.TECHNICAL_SKILLS, "Yêu cầu: Python, FastAPI, Docker, PostgreSQL")]),
    # bare comma-separated technology list
    ("Python, Django, AWS",
     [(MatchDimension.TECHNICAL_SKILLS, "Python, Django, AWS")]),
    # benefits lines are not requirements; the skill line is kept
    ("Lương cao, thưởng tháng 13, bảo hiểm\nRequirements: Go, gRPC",
     [(MatchDimension.TECHNICAL_SKILLS, "Requirements: Go, gRPC")]),
])
def test_mat_03b_unlabelled_requirement_lines_are_extracted(jd, expected):
    """TC-MAT-03b: skill lines without a dimension keyword become technical
    requirements; unrelated lines (title, benefits) are not invented as
    requirements when real requirements exist."""
    reqs = build_job_requirements(JobMatchTarget(description=jd))
    assert [(r.dimension, r.text) for r in reqs] == expected


def test_mat_03c_plain_comma_lists_ignored_when_job_has_structured_skills():
    """TC-MAT-03c: crawled jobs already carry structured skills, so a bare
    comma list (often benefits/perks) is not added as a requirement."""
    reqs = build_job_requirements(JobMatchTarget(
        description="Salary, bonus, insurance", skills=["Python"]))
    assert [r.text for r in reqs] == ["Python"]


def test_mat_03d_jd_without_keywords_falls_back_to_all_lines():
    """TC-MAT-03d: a JD with no recognisable line is never scored against zero
    requirements – every line is used instead."""
    reqs = build_job_requirements(JobMatchTarget(description="Build REST APIs\nWrite tests"))
    assert [(r.dimension, r.text) for r in reqs] == [
        (MatchDimension.TECHNICAL_SKILLS, "Build REST APIs"),
        (MatchDimension.TECHNICAL_SKILLS, "Write tests"),
    ]


@pytest.mark.parametrize("jd", [
    "Thành thạo ít nhất một ngôn ngữ lập trình như Python hoặc Go",
    "Proficient in at least one programming language such as Python or Go",
    "Knowledge of a scripting language (Bash) and a query language (SQL)",
])
def test_mat_04_programming_language_is_a_technical_skill(jd):
    """TC-MAT-04 (BUG-004 fixed): 'ngôn ngữ lập trình' / 'programming language'
    is a technical skill, not a spoken language/certification."""
    (req,) = build_job_requirements(JobMatchTarget(description=jd))
    assert req.dimension == MatchDimension.TECHNICAL_SKILLS


def test_mat_04b_spoken_language_still_language_dimension():
    """TC-MAT-04b: real language requirements keep their dimension."""
    reqs = build_job_requirements(JobMatchTarget(
        description="Tiếng Anh giao tiếp tốt\nIELTS 6.5 or equivalent English level"))
    assert {r.dimension for r in reqs} == {MatchDimension.LANGUAGES_AND_CERTIFICATIONS}


def test_mat_05_decimal_years_and_dotted_names_survive_split():
    """TC-MAT-05 (BUG-010 fixed): '2.5 năm' and 'Node.js' stay inside one
    requirement, and the years check reads 2.5 (not 5)."""
    from app.services.job_matching import required_years

    jd = "Tối thiểu 2.5 năm kinh nghiệm với Node.js và Vue.js"
    texts = [r.text for r in build_job_requirements(JobMatchTarget(description=jd))]
    assert texts == [jd]
    assert required_years(texts[0]) == 2.5


def test_mat_05b_sentences_and_bullets_are_still_split():
    """TC-MAT-05b: real sentence ends and bullets still separate requirements."""
    jd = ("Experience with ASP.NET Core. Bachelor degree in IT.\n"
          "• Knowledge of Docker; Kubernetes skills are a plus\n- 1. Github portfolio")
    texts = [r.text for r in build_job_requirements(JobMatchTarget(description=jd))]
    assert texts == ["Experience with ASP.NET Core", "Bachelor degree in IT",
                     "Knowledge of Docker", "Kubernetes skills are a plus", "Github portfolio"]


@pytest.mark.parametrize(("text", "dimension"), [
    ("Work with international clients", None),
    ("Internship program for students", MatchDimension.EXPERIENCE),
    ("Hands-on experience with microservices", MatchDimension.EXPERIENCE),
    ("Strong skills in SQL", MatchDimension.TECHNICAL_SKILLS),
])
def test_mat_06_keywords_match_whole_words(text, dimension):
    """TC-MAT-06 (BUG-004 fixed): keywords match whole words only – 'intern'
    no longer matches 'international' – while plurals still match."""
    from app.services.job_matching_context import classify_requirement

    assert classify_requirement(text) == dimension


def test_mat_07_long_jd_produces_more_than_30_requirements():
    """TC-MAT-07a: a realistic crawled job easily exceeds 30 requirements."""
    skills = [f"Skill{i}" for i in range(25)]
    jd = "\n".join(f"Experience with system {i}" for i in range(10))
    assert len(build_job_requirements(JobMatchTarget(description=jd, skills=skills))) == 35


async def test_mat_07_matching_succeeds_for_more_than_30_requirements():
    """TC-MAT-07 (BUG-002 fixed): every requirement must be assessed, and the
    evidence list now accepts as many items as there can be requirements."""
    skills = [f"Skill{i}" for i in range(25)]
    jd = "\n".join(f"Experience with system {i}" for i in range(10))
    result = await service(ScriptedAgent()).match(matching_input(jd, skills=skills))
    assert len(result.evidence) == 35
    assert result.overall_score > 0


async def test_mat_07b_requirements_capped_without_dropping_dimensions():
    """TC-MAT-07b: a job with more requirements than the shared limit is
    capped round-robin, so experience/education lines are not dropped behind
    a long skills list, and matching still produces a valid result."""
    from app.schemas.job_matching import MAX_MATCH_REQUIREMENTS

    skills = [f"Skill{i}" for i in range(80)]
    jd = "Tối thiểu 1 năm kinh nghiệm Python\nBachelor degree in IT"
    job = JobMatchTarget(description=jd, skills=skills[:MAX_MATCH_REQUIREMENTS])
    reqs = build_job_requirements(job)
    assert len(reqs) == MAX_MATCH_REQUIREMENTS
    assert {MatchDimension.EXPERIENCE, MatchDimension.EDUCATION} <= {r.dimension for r in reqs}
    data = JobMatchingInput(cv_profile=make_cv_profile(), job=job)
    result = await service(ScriptedAgent()).match(data)
    assert len(result.evidence) == MAX_MATCH_REQUIREMENTS


def test_mat_07c_assessment_and_input_limits_are_consistent():
    """TC-MAT-07c: requirements and evidence share one limit, so a complete
    assessment is always representable."""
    from app.schemas.job_matching import (
        MAX_MATCH_REQUIREMENTS,
        JobMatchingAssessment as Assessment,
    )

    def max_len(model, field):
        return next(m.max_length for m in model.model_fields[field].metadata
                    if hasattr(m, "max_length"))

    assert max_len(JobMatchingInput, "requirements") == MAX_MATCH_REQUIREMENTS
    assert max_len(Assessment, "evidence") == MAX_MATCH_REQUIREMENTS


# --------------------------------------------------------------------------
# Experience years
# --------------------------------------------------------------------------
def _exp(start, end, current=False):
    return WorkExperience(job_title="Dev", company="X", location=None, start_date=start,
                          end_date=end, is_current=current, responsibilities=[],
                          achievements=[])


def test_mat_08_total_years_merges_overlaps():
    """TC-MAT-08: overlapping roles are merged, current role runs to today."""
    profile = make_cv_profile(work_experiences=[
        _exp("01/2020", "01/2022"), _exp("06/2021", "06/2022"),
        _exp("2023-01", None, current=True),
    ])
    # 01/2020..06/2022 merged = 29 months, 01/2023..01/2024 = 12 months -> 41/12
    assert calculate_total_experience_years(profile, today=date(2024, 1, 1)) == 3.4


def test_mat_09_unparseable_dates_are_ignored():
    """TC-MAT-09: 'Hiện tại' without is_current and garbage dates are ignored."""
    profile = make_cv_profile(work_experiences=[_exp("03/2022", "Hiện tại"), _exp("abc", "xyz")])
    assert calculate_total_experience_years(profile) is None


async def test_mat_10_years_check_is_deterministic():
    """TC-MAT-10: '>= N years' decided in code; LLM status is overridden."""
    jd = "Tối thiểu 3 năm kinh nghiệm backend"
    agent = ScriptedAgent(status=MatchStatus.MATCHED)  # LLM wrongly says matched
    result = await service(agent).match(matching_input(jd))  # CV has 2 years
    (item,) = result.evidence
    assert item.status == MatchStatus.PARTIAL
    assert "CV 2 năm" in item.explanation


async def test_mat_11_years_range_uses_lower_bound():
    """TC-MAT-11 (BUG-011 fixed): '2-3 năm kinh nghiệm' -> minimum is 2; CV
    with 2 years matches."""
    result = await service(ScriptedAgent()).match(matching_input("2-3 năm kinh nghiệm Python"))
    assert result.evidence[0].status == MatchStatus.MATCHED


@pytest.mark.parametrize(("text", "years"), [
    ("2-3 năm kinh nghiệm", 2), ("2 – 3 years of experience", 2),
    ("từ 2 đến 4 năm kinh nghiệm", 2), ("3 to 5 years experience", 3),
    ("Kinh nghiệm 1-2 năm", 1), ("at least 3+ years", 3),
    ("Tối thiểu 2,5 năm kinh nghiệm", 2.5), ("Experience with Python 3", None),
])
def test_mat_11b_required_years_parsing(text, years):
    """TC-MAT-11b: ranges use the lower bound; version numbers are not years."""
    from app.services.job_matching import required_years

    assert required_years(text) == years


async def test_mat_11c_years_range_still_flags_insufficient_experience():
    """TC-MAT-11c: the lower bound is still enforced (CV 2 years, '3-5 năm')."""
    result = await service(ScriptedAgent()).match(matching_input("3-5 năm kinh nghiệm Python"))
    assert result.evidence[0].status == MatchStatus.PARTIAL


# --------------------------------------------------------------------------
# Scoring rules
# --------------------------------------------------------------------------
async def test_mat_12_high_medium_low_fit():
    """TC-MAT-12: high / partial / missing evidence map to the expected bands."""
    jd = "Proficient in Python framework.\nBachelor degree in IT"
    high = await service(ScriptedAgent(score=95)).match(matching_input(jd))
    medium = await service(ScriptedAgent(MatchStatus.PARTIAL, score=60)).match(matching_input(jd))
    low = await service(ScriptedAgent(MatchStatus.MISSING, score=0)).match(matching_input(jd))
    assert high.recommendation == MatchRecommendation.STRONG_MATCH
    assert medium.recommendation == MatchRecommendation.PARTIAL_MATCH
    assert (low.overall_score, low.recommendation) == (0.0, MatchRecommendation.LOW_MATCH)


async def test_mat_13_weights_renormalised_over_applicable_dimensions():
    """TC-MAT-13: only dimensions with requirements count (0.40/0.50 & 0.10/0.50)."""
    jd = "Proficient in Python framework.\nBachelor degree in IT"
    agent = ScriptedAgent(per_requirement={"Bachelor": MatchStatus.MISSING}, score=100)
    result = await service(agent).match(matching_input(jd))
    assert result.overall_score == 80.0


async def test_mat_14_mandatory_requirement_caps_score():
    """TC-MAT-14: a missing 'bắt buộc' requirement caps the score at 49.99."""
    jd = "Proficient in Python framework.\nChứng chỉ AWS là bắt buộc"
    agent = ScriptedAgent(per_requirement={"AWS": MatchStatus.MISSING}, score=100)
    result = await service(agent).match(matching_input(jd))
    assert result.overall_score == 49.99
    assert result.recommendation == MatchRecommendation.LOW_MATCH


async def test_mat_15_optional_requirement_does_not_cap_score():
    """TC-MAT-15 (BUG-012 fixed): 'Tiếng Anh: không bắt buộc' is optional and
    must not cap the score."""
    jd = "Proficient in Python framework.\nTiếng Anh không bắt buộc"
    agent = ScriptedAgent(per_requirement={"Tiếng Anh": MatchStatus.MISSING}, score=100)
    result = await service(agent).match(matching_input(jd))
    assert result.overall_score > 49.99


@pytest.mark.parametrize(("text", "mandatory"), [
    ("Chứng chỉ AWS là bắt buộc", True), ("Must have Docker", True),
    ("Required: 3 years of Go", True), ("Tiếng Anh không bắt buộc", False),
    ("AWS certification not required", False), ("Kubernetes: optional", False),
    ("Docker is a plus, not mandatory", False), ("Non-mandatory: GraphQL", False),
    ("Biết React là lợi thế", False), ("Preferred: master degree", False),
])
def test_mat_15b_mandatory_detection_handles_negation(text, mandatory):
    """TC-MAT-15b: negated / optional wording is never treated as mandatory."""
    from app.services.job_matching import is_mandatory_requirement

    assert is_mandatory_requirement(text) is mandatory


async def test_mat_16_evidence_text_resolved_from_catalog():
    """TC-MAT-16: explanation evidence is copied from the CV catalog, not the LLM."""
    result = await service(ScriptedAgent()).match(
        matching_input("x", skills=["Python"])
    )
    assert result.evidence[0].cv_evidence[0] in {
        item.text for item in build_cv_evidence_catalog(make_cv_profile())
    }


async def test_mat_17_consistency_and_cache():
    """TC-MAT-17: identical input -> identical score, second call is a cache hit."""
    agent = ScriptedAgent()
    svc = service(agent)
    first = await svc.match(matching_input("Proficient in Python framework"))
    second = await svc.match(matching_input("Proficient in Python framework"))
    assert first.overall_score == second.overall_score
    assert (agent.calls, second.cache_hit) == (1, True)


async def test_mat_18_concurrent_identical_requests_are_coalesced():
    """TC-MAT-18: concurrent identical matches share one LLM call."""
    agent = ScriptedAgent(delay=0.05)
    svc = service(agent)
    results = await asyncio.gather(*[
        svc.match(matching_input("Proficient in Python framework")) for _ in range(5)
    ])
    assert agent.calls == 1
    assert len({r.overall_score for r in results}) == 1


async def test_mat_19_cancelled_waiter_does_not_poison_cache():
    """TC-MAT-19: a cancelled request cancels the in-flight task; retry works."""
    agent = ScriptedAgent(delay=0.2)
    svc = service(agent)
    task = asyncio.create_task(svc.match(matching_input("Proficient in Python framework")))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = await svc.match(matching_input("Proficient in Python framework"))
    assert result.overall_score > 0 and agent.calls == 2


def test_mat_20_invalid_weights_rejected():
    """TC-MAT-20: weights must cover all dimensions and sum to 1."""
    with pytest.raises(ValueError):
        JobMatchingService(agent=ScriptedAgent(),
                           dimension_weights={MatchDimension.TECHNICAL_SKILLS: 1.0})


def test_mat_21_jd_missing_information_is_rejected():
    """TC-MAT-21: empty JD is rejected by schema validation."""
    with pytest.raises(ValidationError):
        JobMatchTarget(description="   ")


def test_mat_22_schema_rejects_score_without_evidence():
    """TC-MAT-22: a positive dimension score with no matched evidence is invalid."""
    with pytest.raises(ValidationError):
        JobMatchingAssessment.model_validate({
            "breakdown": {f: 50 for f in FIELD.values()}, "evidence": [],
            "summary": "x", "confidence": 0.5,
        })


def test_mat_23_cv_without_skills_still_builds_catalog():
    """TC-MAT-23: CV missing skills -> catalog still has experience/education."""
    catalog = build_cv_evidence_catalog(make_cv_profile(skills=[]))
    assert {i.dimension for i in catalog} >= {MatchDimension.EXPERIENCE, MatchDimension.EDUCATION}


def test_mat_24_personal_data_excluded_from_llm_payload():
    """TC-MAT-24: contact details never reach the matching prompt."""
    from app.utils.cv_privacy import cv_profile_for_llm

    payload = cv_profile_for_llm(make_cv_profile(), purpose="job_matching")
    assert "personal_information" not in payload
    letter = cv_profile_for_llm(make_cv_profile(), purpose="cover_letter")
    assert letter["personal_information"] == {"full_name": "Nguyen Van Test"}
