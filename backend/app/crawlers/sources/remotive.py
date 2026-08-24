from datetime import UTC, datetime

import httpx
from app.schemas.job import (
    CrawlPage,
    EmploymentType,
    JobCandidate,
    RawJob,
    SeniorityLevel,
    WorkMode,
)
from app.utils.html import html_to_text
from pydantic import BaseModel, ConfigDict, Field


class RemotiveJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | str
    url: str
    title: str
    company_name: str
    company_logo: str | None = None
    category: str | None = None
    job_type: str | None = None
    publication_date: datetime | None = None
    candidate_required_location: str | None = None
    salary: str | None = None
    description: str | None = None

class RemotiveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    job_count: int = Field(default=0, alias="job-count")
    jobs: list[RemotiveJob] = Field(default_factory=list)

class RemotiveJobSource:
    source_name = "remotive"

    _API_URL = "https://remotive.com/api/remote-jobs"
    _MAX_LIMIT = 100

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_page(self, *, cursor: str | None = None, limit: int = 20) -> CrawlPage:
        if cursor is not None:
            raise ValueError("Remotive does not support cursor paginations.")

        if limit < 1 or limit > self._MAX_LIMIT:
            raise ValueError(
                f"Remotive limit must be between "
                f"1 and {self._MAX_LIMIT}."
            )

        response = await self._client.get(
            self._API_URL,
            params={"limit": limit},
        )
        response.raise_for_status()

        page = RemotiveResponse.model_validate(response.json())

        raw_jobs = [
            RawJob(
                source=self.source_name,
                source_job_id=str(job.id),
                source_url=job.url,
                payload=job.model_dump(mode="json", exclude_none=False),
            )
            for job in page.jobs
        ]

        return CrawlPage(items=raw_jobs, next_cursor=None)

    def map_to_candidate(self, raw_job: RawJob) -> JobCandidate:
        job = RemotiveJob.model_validate(raw_job.payload)
        description = html_to_text(job.description)
        location = job.candidate_required_location or "Worldwide"
        skills = [job.category] if job.category else []

        return JobCandidate(
            source=self.source_name,
            source_job_id=str(job.id),
            source_url=job.url,
            title=job.title,
            company=job.company_name,
            description=description,
            location=location,
            employment_type=self._map_employment_type(job.job_type),
            work_mode=WorkMode.REMOTE,
            seniority_level=SeniorityLevel.UNKNOWN,
            skills=skills,
            posted_at=self._to_utc(job.publication_date),
            source_metadata={
                "company_logo": job.company_logo,
                "category": job.category,
                "salary_text": job.salary,
                "attribution": "Remotive",
                "attribution_url": job.url ,
            },
        )

    @staticmethod
    def _map_employment_type(value: str | None) -> EmploymentType:
        mapping = {
            "full_time": EmploymentType.FULL_TIME,
            "part_time": EmploymentType.PART_TIME,
            "contract": EmploymentType.CONTRACT,
            "freelance": EmploymentType.FREELANCE,
            "internship": EmploymentType.INTERNSHIP,
        }

        normalized = (value or "").strip().casefold()

        return mapping.get(normalized, EmploymentType.OTHER)

    @staticmethod
    def _to_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)
    
