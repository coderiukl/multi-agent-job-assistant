from app.agents.job_search_agent import JobSearchAgent
from app.repositories.postgres_job_search import PostgresJobSearchRepository
from app.vectorstores.base import JobVectorIndex
from app.schemas.job_search import JobSearchRequest, JobSearchResult
import asyncio

class HybridJobSearchService:
    def __init__(
        self,
        *,
        agent: JobSearchAgent,
        repository: PostgresJobSearchRepository,
        vector_index: JobVectorIndex,
        candidate_limit: int = 100
    ) -> None:
        self._agent = agent
        self._repository = repository
        self._vector_index = vector_index
        self._candidate_limit = candidate_limit

    async def search(self, request: JobSearchRequest) -> JobSearchResult:
        plan = await self._agent.analyze(request)

        postgres_jobs, semantic_hits = await asyncio.gather(
            self._repository.search_candidates(
                plan=plan,
                limit=self._candidate_limit,
            ),
            self._vector_index.search_jobs(
                query=plan.semantic_query,
                limit=self._candidate_limit,
            ),
        )

        semantic_jobs = await self._repository.get_by_ids(
            job_ids=[hit.job_id for hit in semantic_hits],
            plan=plan
        )