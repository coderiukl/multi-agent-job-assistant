from typing import Protocol, runtime_checkable

from app.schemas.job import CrawlPage, JobCandidate, RawJob

@runtime_checkable
class JobSource(Protocol):
    @property
    def source_name(self) -> str:
        ...

    async def fetch_page(self, *, cursor: str | None = None, limit: int = 20) -> CrawlPage:
        ...

    def map_to_candidate(self, raw_job: RawJob) -> JobCandidate:
        ...
