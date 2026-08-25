from typing import Protocol

from app.schemas.job_search import (
    JobSearchPage,
    JobSearchPlan,
)


class JobSearchRepository(Protocol):
    async def search(self, *, plan: JobSearchPlan, page: int, page_size: int) -> JobSearchPage:
        ...