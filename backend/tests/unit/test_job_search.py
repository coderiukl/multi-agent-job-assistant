"""Job Search Agent / hybrid retrieval tests (Phase 2B).

HybridJobSearchService runs for real; the query-understanding LLM agent, the
PostgreSQL repository and the Qdrant index are fakes with controllable output.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.job_search_agent import JobSearchAgent
from app.core.exceptions import ExternalServiceException, StorageException
from app.schemas.job import SeniorityLevel
from app.schemas.job_search import (
    JobSearchFilters,
    JobSearchPlan,
    JobSearchRequest,
    JobSearchSort,
    JobSearchStrategy,
    JobVectorSearchHit,
)
from app.services.job_search import HybridJobSearchService
from tests.conftest import make_job


class FakePlanner:
    def __init__(self, keywords=None, filters=None, fail: Exception | None = None):
        self.keywords = keywords or ["Python"]
        self.filters = filters
        self.fail = fail

    async def analyze(self, request, context=None):
        if self.fail:
            raise self.fail
        return JobSearchPlan(original_query=request.query, semantic_query=request.query,
                             keywords=self.keywords,
                             filters=self.filters or request.filters)


class FakeRepository:
    def __init__(self, candidates=None, by_id=None, fail: Exception | None = None):
        self.candidates = candidates or []
        self.by_id = {job.job_id: job for job in (by_id or [])}
        self.fail = fail
        self.plans = []

    async def search_candidates(self, *, plan, limit):
        self.plans.append(plan)
        if self.fail:
            raise self.fail
        return self.candidates[:limit]

    async def get_by_ids(self, *, job_ids, plan):
        return [self.by_id[j] for j in job_ids if j in self.by_id]


class FakeVectors:
    def __init__(self, hits=None, fail: Exception | None = None):
        self.hits = hits or []
        self.fail = fail

    async def search_jobs(self, *, query, limit, filters=None):
        if self.fail:
            raise self.fail
        return self.hits[:limit]


def build(planner=None, repo=None, vectors=None) -> HybridJobSearchService:
    return HybridJobSearchService(agent=planner or FakePlanner(), repository=repo or FakeRepository(),
                                  vector_index=vectors or FakeVectors(), candidate_limit=100)


def request(query="Python Backend Intern HCM", **kwargs) -> JobSearchRequest:
    return JobSearchRequest(query=query, **kwargs)


async def test_srch_01_hybrid_merges_postgres_and_semantic():
    """TC-SRCH-01: candidates from both sources merged, HYBRID strategy."""
    a, b = make_job(1, title="Python Backend Intern"), make_job(2, title="Data Engineer")
    service = build(repo=FakeRepository([a], by_id=[b]),
                    vectors=FakeVectors([JobVectorSearchHit(job_id=b.job_id, score=0.9)]))
    result = await service.search(request())
    assert result.strategy == JobSearchStrategy.HYBRID
    assert {h.job.job_id for h in result.items} == {a.job_id, b.job_id}


async def test_srch_02_qdrant_failure_falls_back_to_postgres():
    """TC-SRCH-02: Qdrant unavailable -> POSTGRES strategy, still returns jobs."""
    job = make_job(1)
    service = build(repo=FakeRepository([job]),
                    vectors=FakeVectors(fail=ExternalServiceException(service="qdrant")))
    result = await service.search(request())
    assert result.strategy == JobSearchStrategy.POSTGRES
    assert result.items[0].job.job_id == job.job_id


async def test_srch_03_llm_failure_uses_keyword_fallback_plan():
    """TC-SRCH-03: query analyzer down -> deterministic keyword plan."""
    repo = FakeRepository([make_job(1)])
    service = build(planner=FakePlanner(fail=ExternalServiceException(service="llm")), repo=repo)
    await service.search(request("Tìm việc Python Backend ở Hà Nội"))
    assert repo.plans[0].keywords == ["Python", "Backend", "Hà", "Nội"]
    assert repo.plans[0].confidence == 0.0


async def test_srch_04_postgres_failure_is_raised():
    """TC-SRCH-04: PostgreSQL failure is not silently swallowed (500 to client)."""
    service = build(repo=FakeRepository(fail=StorageException(message="db down")))
    with pytest.raises(StorageException):
        await service.search(request())


async def test_srch_05_no_results():
    """TC-SRCH-05: nothing matches -> empty items, total 0, has_more False."""
    result = await build().search(request("Golang Rust Elixir"))
    assert (result.total, result.items, result.has_more) == (0, [], False)


async def test_srch_06_cross_source_duplicates_are_removed():
    """TC-SRCH-06: same title/company/location from two sources -> one hit."""
    a = make_job(1, source="topdev", title="Python Dev", company="Acme")
    b = make_job(1, source="itviec", title="Python Dev", company="Acme")
    result = await build(repo=FakeRepository([a, b])).search(request())
    assert result.total == 1


async def test_srch_07_pagination():
    """TC-SRCH-07: page 2 returns the next slice."""
    jobs = [make_job(i, title=f"Python Dev {i}", company=f"C{i}") for i in range(15)]
    result = await build(repo=FakeRepository(jobs)).search(request(page=2, page_size=10))
    assert (result.page, len(result.items), result.total) == (2, 5, 15)


async def test_srch_08_newest_sort():
    """TC-SRCH-08: sort=newest orders by posting date."""
    old = make_job(1, title="Python A", company="A", posted_days_ago=30)
    new = make_job(2, title="Python B", company="B", posted_days_ago=1)
    result = await build(repo=FakeRepository([old, new])).search(
        request(sort=JobSearchSort.NEWEST))
    assert [h.job.job_id for h in result.items] == [new.job_id, old.job_id]


async def test_srch_09_semantic_hit_not_outranked_by_unscored_candidate():
    """TC-SRCH-09 (BUG-013 fixed): a strong semantic + keyword hit outranks a
    candidate Qdrant did not return; both are scored with one formula."""
    strong = make_job(1, title="Python Backend Intern", company="A")
    other = make_job(2, title="Python Backend Intern", company="B",
                     description="Python Backend Intern HCM role")
    service = build(planner=FakePlanner(keywords=["Python", "Backend", "Intern", "HCM"]),
                    repo=FakeRepository([other], by_id=[strong]),
                    vectors=FakeVectors([JobVectorSearchHit(job_id=strong.job_id, score=0.95)]))
    result = await service.search(request())
    assert result.items[0].job.job_id == strong.job_id
    strong_hit, other_hit = result.items
    assert other_hit.score.semantic is None  # not invented, just not retrieved
    expected = round(0.3 * other_hit.score.keyword + 0.1 * other_hit.score.freshness, 6)
    assert other_hit.score.final == expected


async def test_srch_09b_postgres_only_search_keeps_reweighted_scale():
    """TC-SRCH-09b: when Qdrant is down every candidate is PostgreSQL-only, so
    the keyword/freshness re-weighting still ranks them on one scale."""
    job = make_job(1, title="Python Backend Intern")
    service = build(planner=FakePlanner(keywords=["Python"]), repo=FakeRepository([job]),
                    vectors=FakeVectors(fail=ExternalServiceException(service="qdrant")))
    (hit,) = (await service.search(request())).items
    assert hit.score.final == round(0.75 * hit.score.keyword + 0.25 * hit.score.freshness, 6)


async def test_srch_10_reasons_are_grounded_in_job_data():
    """TC-SRCH-10 (BUG-031 fixed): no 'Phù hợp với cấp độ...' reason for an
    'unknown' job; filter_match reflects what the job data really satisfies."""
    unknown = make_job(1, title="Python A", company="A", seniority=SeniorityLevel.UNKNOWN)
    senior = make_job(2, title="Python B", company="B", seniority=SeniorityLevel.SENIOR)
    filters = JobSearchFilters(seniority_levels=[SeniorityLevel.SENIOR],
                               locations=["TP.HCM"])
    result = await build(planner=FakePlanner(filters=filters),
                         repo=FakeRepository([unknown, senior])).search(request(filters=filters))
    hits = {hit.job.job_id: hit for hit in result.items}
    seniority_reason = "Phù hợp với cấp độ kinh nghiệm được yêu cầu."
    assert seniority_reason not in hits[unknown.job_id].reasons
    assert seniority_reason in hits[senior.job_id].reasons
    assert "Phù hợp với địa điểm yêu cầu." in hits[senior.job_id].reasons
    assert hits[senior.job_id].score.filter_match == 1.0
    assert hits[unknown.job_id].score.filter_match == 0.75  # location yes, seniority unknown


async def test_srch_10b_no_filters_means_full_filter_match():
    """TC-SRCH-10b: without active filters filter_match is 1.0 (nothing violated)."""
    (hit,) = (await build(repo=FakeRepository([make_job(1)])).search(request())).items
    assert hit.score.filter_match == 1.0


def test_srch_11_salary_filter_requires_currency_and_period():
    """TC-SRCH-11: salary filters without currency/period are rejected (422)."""
    with pytest.raises(ValidationError):
        JobSearchFilters(salary_min=20_000_000)
    with pytest.raises(ValidationError):
        JobSearchFilters(salary_min=30, salary_max=10, salary_currency="VND",
                         salary_period="monthly")
    ok = JobSearchFilters(salary_min=20_000_000, salary_currency="vnd", salary_period="monthly")
    assert ok.salary_currency == "VND"


def test_srch_12_request_validation():
    """TC-SRCH-12: empty / oversized query and bad pagination are rejected."""
    for kwargs in ({"query": "   "}, {"query": "x" * 2001}, {"query": "a", "page": 0},
                   {"query": "a", "page_size": 51}):
        with pytest.raises(ValidationError):
            JobSearchRequest(**kwargs)


def test_srch_13_explicit_filters_override_llm_inference():
    """TC-SRCH-13: explicit app filters are never weakened by the LLM plan."""
    explicit = JobSearchRequest(query="python", filters=JobSearchFilters(locations=["Hà Nội"]))
    inferred = JobSearchPlan(original_query="python", semantic_query="python",
                             filters=JobSearchFilters(locations=["Hồ Chí Minh"],
                                                      skills=["Python"]))
    plan = JobSearchAgent._apply_request_constraints(request=explicit, plan=inferred)
    assert plan.filters.locations == ["Hà Nội"]
    assert plan.filters.skills == ["Python"]


async def test_srch_14_has_more_false_beyond_retrieval_window():
    """TC-SRCH-14 (BUG-031 fixed): once the 500-candidate window is exhausted
    no further page can be returned, so has_more is False (no infinite 'load
    more'); the last full page of the window also reports has_more False."""
    jobs = [make_job(i, title=f"Python {i}", company=f"C{i}") for i in range(500)]
    service = build(repo=FakeRepository(jobs))
    beyond = await service.search(request(page=60, page_size=10))
    assert beyond.items == [] and beyond.has_more is False
    last = await service.search(request(page=50, page_size=10))
    assert len(last.items) == 10 and last.has_more is False


async def test_srch_14b_saturated_small_window_still_has_more():
    """TC-SRCH-14b: a saturated window below the cap still offers more pages
    (the next page is retrieved with a bigger window)."""
    jobs = [make_job(i, title=f"Python {i}", company=f"C{i}") for i in range(150)]
    first = await build(repo=FakeRepository(jobs)).search(request(page=1, page_size=10))
    assert first.has_more is True
