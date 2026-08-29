import asyncio
import logging
import re
import unicodedata
from datetime import UTC, datetime
from typing import cast

from app.agents.job_search_agent import JobSearchAgent
from app.repositories.postgres_job_search import PostgresJobSearchRepository
from app.schemas.job import NormalizedJob, normalize_single_line
from app.schemas.job_search import (
    JobSearchRequest, 
    JobSearchResult,
    JobSearchHit,
    JobSearchPlan,
    JobSearchScore,
    JobSearchSort,
    JobSearchStrategy,
    JobVectorSearchHit
)
from app.vectorstores.base import JobVectorIndex

LOGGER = logging.getLogger(__name__)

MAX_CANDIDATE_LIMIT = 500

SEMANTIC_WEIGHT = 0.60
KEYWORD_WEIGHT = 0.30
FRESHNESS_WEIGHT = 0.10

FRESHNESS_WINDOW_DAYS = 90.0

class HybridJobSearchService:
    def __init__(
        self,
        *,
        agent: JobSearchAgent,
        repository: PostgresJobSearchRepository,
        vector_index: JobVectorIndex,
        candidate_limit: int = 100
    ) -> None:
        if not 1 <= candidate_limit <= MAX_CANDIDATE_LIMIT:
            raise ValueError(f"candidate_limit must be between 1 and {MAX_CANDIDATE_LIMIT}")
        
        self._agent = agent
        self._repository = repository
        self._vector_index = vector_index
        self._candidate_limit = candidate_limit

    async def search(self, request: JobSearchRequest) -> JobSearchResult:
        plan = await self._agent.analyze(request)

        retrieval_limit = self._resolve_retrieval_limit(request)

        postgres_result, semantic_result = await asyncio.gather(
            self._repository.search_candidates(
                plan=plan,
                limit=retrieval_limit
            ),
            self._vector_index.search_jobs(
                query=plan.semantic_query,
                limit=retrieval_limit
            ),
            return_exceptions=True
        )

        if isinstance(postgres_result, BaseException):
            raise postgres_result

        postgres_jobs = cast(list[NormalizedJob], postgres_result)

        semantic_available = True

        if isinstance(semantic_result, BaseException):
            if isinstance(semantic_result, asyncio.CancelledError):
                raise semantic_result

            semantic_available = False
            semantic_hits: list[JobVectorSearchHit] = []
        
            LOGGER.warning(
                "Semantic job retrieval failed; "
                "falling back to PostgreSQL candidates",
                extra={
                    "error_type": type(
                        semantic_result
                    ).__name__,
                },
                exc_info=semantic_result,
            )

        else:
            semantic_hits = cast(list[JobVectorSearchHit], semantic_result)

        semantic_jobs = await self._load_semantic_jobs(
            plan=plan,
            semantic_hits=semantic_hits
        )

        semantic_scores = self._build_semantic_scores(semantic_hits)

        merged_jobs = self._merge_jobs(
            postgres_jobs=postgres_jobs,
            semantic_jobs=semantic_jobs,
        )

        ranked_hits = [
            self._build_search_hit(
                job=job,
                plan=plan,
                semantic_score=semantic_scores.get(job.job_id)
            )
            for job in merged_jobs
        ]

        deduplicated_hits = self._deduplicate_hits(ranked_hits)

        sorted_hits = self._sort_hits(hits=deduplicated_hits, sort=request.sort)

        total = len(sorted_hits)

        page_items = self._paginate_hits(
            hits=sorted_hits,
            page=request.page,
            page_size=request.page_size
        )

        strategy = JobSearchStrategy.HYBRID if semantic_available else JobSearchStrategy.POSTGRES

        LOGGER.info(
            "Hybrid job search completed",
            extra={
                "query": request.query,
                "strategy": strategy.value,
                "postgres_candidates": len(postgres_jobs),
                "semantic_candidates": len(semantic_jobs),
                "merged_candidates": len(merged_jobs),
                "deduplicated_candidates": total,
                "page": request.page,
                "page_size": request.page_size,
            },
        )

        return JobSearchResult(
            query=request.query,
            strategy=strategy,
            total=total,
            page=request.page,
            page_size=request.page_size,
            items=page_items
        )

    async def _load_semantic_jobs(self, *, plan: JobSearchPlan, semantic_hits: list[JobVectorSearchHit]) -> list[NormalizedJob]:
        if not semantic_hits:
            return []

        job_ids = [hit.job_id for hit in semantic_hits]

        return await self._repository.get_by_ids(
            job_ids=job_ids,
            plan=plan,
        )

    @staticmethod
    def _build_semantic_scores(hits: list[JobVectorSearchHit]) -> dict[str, float]:
        scores: dict[str, float] = {}

        for hit in hits:
            normalized_score = HybridJobSearchService._clamp_score(hit.score)

            previous_score = scores.get(hit.job_id)

            if previous_score is None or normalized_score > previous_score:
                scores[hit.job_id] = normalized_score

        return scores

    @staticmethod
    def _merge_jobs(*, postgres_jobs: list[NormalizedJob], semantic_jobs: list[NormalizedJob]) -> list[NormalizedJob]:
        jobs_by_id: dict[str, NormalizedJob] = {}

        for job in postgres_jobs:
            jobs_by_id[job.job_id] = job

        for job in semantic_jobs:
            jobs_by_id[job.job_id] = job

        return list(jobs_by_id.values())

    def _build_search_hit(self, *, job: NormalizedJob, plan: JobSearchPlan, semantic_score: float | None) -> JobSearchHit:
        keyword_score, matched_terms = self._calculate_keyword_score(
            job=job,
            keywords=plan.keywords,
        )

        freshness_score = self._calculate_freshness_score(job)

        final_score = self._calculate_final_score(
            semantic_score=semantic_score,
            keyword_score=keyword_score,
            freshness_score=freshness_score,
        )

        reasons = self._build_reasons(
            job=job,
            plan=plan,
            semantic_score=semantic_score,
            matched_terms=matched_terms,
            freshness_score=freshness_score,
        )

        return JobSearchHit(
            job=job,
            score=JobSearchScore(
                semantic=semantic_score,
                keyword=keyword_score,
                filter_match=1.0,
                freshness=freshness_score,
                final=final_score,
            ),
            matched_terms=matched_terms,
            reasons=reasons,
        )

    @classmethod
    def _calculate_keyword_score(cls, *, job: NormalizedJob, keywords: list[str]) -> tuple[float, list[str]]:
        if not keywords:
            return 0.0, []

        title_and_skills = normalize_single_line(
            " ".join(
                [
                    job.title,
                    *job.skills,
                ]
            )
        ).casefold()

        complete_text = normalize_single_line(
            " ".join(
                [
                    job.title,
                    job.company,
                    job.description,
                    job.location or "",
                    *job.skills,
                ]
            )
        ).casefold()

        accumulated_score = 0.0
        matched_terms: list[str] = []

        for keyword in keywords:
            normalized_keyword = normalize_single_line(keyword).casefold()

            if not normalized_keyword:
                continue

            if cls._contains_term(
                text=title_and_skills,
                term=normalized_keyword,
            ):
                accumulated_score += 1.0
                matched_terms.append(keyword)
                continue

            if cls._contains_term(
                text=complete_text,
                term=normalized_keyword,
            ):
                accumulated_score += 0.5
                matched_terms.append(keyword)

        score = accumulated_score / len(keywords)

        return (
            cls._clamp_score(score),
            list(dict.fromkeys(matched_terms)),
        )

    @staticmethod
    def _contains_term(*, text: str, term: str) -> bool:
        pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
        return re.search(pattern, text, flags=re.IGNORECASE)

    @classmethod
    def _calculate_freshness_score(cls, job: NormalizedJob) -> float:
        posted_at = job.posted_at

        if posted_at is None:
            return 0.2

        normalized_posted_at = cls._ensure_utc(posted_at)
        
        age_seconds = max(0.0, (datetime.now(UTC) - normalized_posted_at).total_seconds())
        age_days = age_seconds / 86_400.0
        score = 1.0 - age_days / FRESHNESS_WINDOW_DAYS
        return cls._clamp_score(score)

    @classmethod
    def _calculate_final_score(cls, *, semantic_score: float | None, keyword_score: float, freshness_score: float) -> float:
        if semantic_score is None:
            score = keyword_score * 0.75 + freshness_score * 0.25
            return cls._round_score(score)

        socre = semantic_score * SEMANTIC_WEIGHT + keyword_score * KEYWORD_WEIGHT + freshness_score * FRESHNESS_WEIGHT
        return cls._round_score(score)

    @staticmethod
    def _build_reasons(
        *,
        job: NormalizedJob,
        plan: JobSearchPlan,
        semantic_score: float | None,
        matched_terms: list[str],
        freshness_score: float
    ) -> list[str]:
        reasons: list[str] = []

        if semantic_score is not None and semantic_score >= 0.75:
            reasons.append("Nội dung công việc phù hợp cao với yêu cầu tìm kiếm.")

        elif semantic_score is not None and semantic_score >= 0.50:
            reasons.append("Nội dung công việc có liên quan đến yêu cầu tìm kiếm.")

        if matched_terms:
            reasons.append("Khớp từ khóa: " + ", ".join(matched_terms[:5]) + ".")

        if plan.filters.locations and job.location:
            reasons.append("Phù hợp với địa điểm yêu cầu.")

        if plan.filters.seniority_levels:
            reasons.append("Phù hợp vợi cấp độ kinh nghiệm được yêu cầu.")

        if freshness_score >= 0.70:
            reasons.append("Công việc được đăng gần đây.")
        
        if not reasons:
            reasons.append("Phù hợp với các bộ lọc tìm kiếm.")

        return reasons

    @classmethod
    def deduplicate_hits(cls, hits: list[JobSearchHit]) -> list[JobSearchHit]:
        best_hits: dict[str, JobSearchHit] = {}

        for hit in hits:
            key = cls._build_deduplication_key(hit.job)

            current = best_hits.get(key)

            if current is None or cls._is_better_hits(candidate=hit, current=current):
                best_hits[key] = hit

        return list(best_hits.values())

    @classmethod
    def _build_deduplication_key(cls, job: NormalizedJob) -> str:
        normalized_title = cls._normalize_deduplication_text(job.title)

        normalized_company = cls._normalize_deduplication_text(job.company)
        
        normalized_location = cls._normalize_deduplication_text(job.location or "")

        return "|".join(
            [
                normalized_title,
                normalized_company,
                normalized_location,
            ]
        )

    @staticmethod
    def _normalize_deduplication_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)

        without_accents = "".join(
            character
            for character in normalized
            if not unicodedata.combining(
                character
            )
        )

        lowercase = without_accents.casefold()

        return re.sub(r"[^a-z0-9]+", " ", lowercase).strip()

    @classmethod
    def _is_better_hit(cls, *, candidate: JobSearchHit, current: JobSearchHit) -> bool:
        candidate_priority = (
            candidate.score.final,
            cls._job_timestamp(candidate.job),
        )

        current_priority = (
            current.score.final,
            cls._job_timestamp(current.job),
        )

        return candidate_priority > current_priority

    @classmethod
    def _sort_hits(cls, *, hits: list[JobSearchHit], sort: JobSearchSort) -> list[JobSearchHit]:
        if sort == JobSearchSort.NEWEST:
            return sorted(
                hits,
                key=lambda hit: (
                    cls._job_timestamp(hit.job),
                    hit.score.final,
                ),
                reverse=True
            )

        return sorted(
            hits,
            key=lambda hit: (
                hit.score.final,
                cls._job_timestamp(hit.job),
            ),
            reverse=True,
        )

    @classmethod
    def _paginate_hits(*, hits: list[JobSearchHit], page: int, page_size: int) -> list[JobSearchHit]:
        start = (page - 1) * page_size

        end = start + page_size

        return hits[start:end]

    def _resolve_retrieval_limit(self, request: JobSearchRequest) -> int:
        required_candidates = request.page * request.page_size * 3

        return min(
            MAX_CANDIDATE_LIMIT,
            max(self._candidate_limit, required_candidates),
        )

    @classmethod
    def _job_timestamp(cls, job: NormalizedJob) -> float:
        timestamp_source = (
            job.posted_at
            or job.crawled_at
        )

        return cls._ensure_utc(timestamp_source).timestamp()

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)

    @staticmethod
    def _clamp_score(score: float) -> float:
        return max(
            0.0,
            min(1.0, float(score)),
        )

    @classmethod
    def _round_score(cls, score: float) -> float:
        return round(cls._clamp_score(score), 6)