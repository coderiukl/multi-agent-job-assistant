from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.schemas.job import (
    CrawlPage,
    EmploymentType,
    JobCandidate,
    RawJob,
    SeniorityLevel,
    WorkMode,
)
from app.utils.html import html_to_text


class ArbeitnowJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    slug: str
    company_name: str
    title: str
    description: str | None = None
    remote: bool = False
    url: str
    tags: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=list)
    location: str | None = None
    created_at: int | float | None = None

    @field_validator(
        "tags",
        "job_types",
        mode="before",
    )
    @classmethod
    def normalize_list(
        cls,
        value: Any,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        return list(value)


class ArbeitnowLinks(BaseModel):
    model_config = ConfigDict(extra="allow")

    next: str | None = None


class ArbeitnowMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    current_page: int = 1
    last_page: int | None = None


class ArbeitnowResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[ArbeitnowJob] = Field(
        default_factory=list
    )
    links: ArbeitnowLinks | None = None
    meta: ArbeitnowMeta | None = None


class ArbeitnowJobSource:
    source_name = "arbeitnow"

    _API_URL = (
        "https://www.arbeitnow.com/api/job-board-api"
    )
    _MAX_LIMIT = 100

    def __init__(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        self._client = client

    async def fetch_page(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CrawlPage:
        if limit < 1 or limit > self._MAX_LIMIT:
            raise ValueError(
                f"Arbeitnow limit must be between "
                f"1 and {self._MAX_LIMIT}."
            )

        page_number = self._parse_cursor(cursor)

        response = await self._client.get(
            self._API_URL,
            params={"page": page_number},
        )
        response.raise_for_status()

        page = ArbeitnowResponse.model_validate(
            response.json()
        )

        selected_jobs = page.data[:limit]

        raw_jobs = [
            RawJob(
                source=self.source_name,
                source_job_id=job.slug,
                source_url=job.url,
                payload=job.model_dump(
                    mode="json",
                    exclude_none=False,
                ),
            )
            for job in selected_jobs
        ]

        return CrawlPage(
            items=raw_jobs,
            next_cursor=self._build_next_cursor(
                page=page,
                current_page=page_number,
            ),
        )

    def map_to_candidate(
        self,
        raw_job: RawJob,
    ) -> JobCandidate:
        job = ArbeitnowJob.model_validate(
            raw_job.payload
        )

        description = html_to_text(
            job.description
        )

        return JobCandidate(
            source=self.source_name,
            source_job_id=job.slug,
            source_url=job.url,
            title=job.title,
            company=job.company_name,
            description=description,
            location=job.location,
            employment_type=(
                self._map_employment_type(
                    job.job_types
                )
            ),
            work_mode=(
                WorkMode.REMOTE
                if job.remote
                else WorkMode.UNKNOWN
            ),
            seniority_level=SeniorityLevel.UNKNOWN,
            skills=job.tags,
            posted_at=self._to_datetime(
                job.created_at
            ),
            source_metadata={
                "slug": job.slug,
                "remote": job.remote,
                "tags": job.tags,
                "job_types": job.job_types,
                "attribution": "Arbeitnow",
                "attribution_url": job.url,
            },
        )

    @staticmethod
    def _parse_cursor(
        cursor: str | None,
    ) -> int:
        if cursor is None:
            return 1

        normalized = cursor.strip()

        if not normalized:
            return 1

        try:
            page_number = int(normalized)
        except ValueError as error:
            raise ValueError(
                "Arbeitnow cursor must be "
                "a positive page number."
            ) from error

        if page_number < 1:
            raise ValueError(
                "Arbeitnow cursor must be "
                "a positive page number."
            )

        return page_number

    @staticmethod
    def _build_next_cursor(
        *,
        page: ArbeitnowResponse,
        current_page: int,
    ) -> str | None:
        if page.links and page.links.next:
            return str(current_page + 1)

        if (
            page.meta
            and page.meta.last_page is not None
            and page.meta.current_page
            < page.meta.last_page
        ):
            return str(page.meta.current_page + 1)

        return None

    @staticmethod
    def _map_employment_type(
        values: list[str],
    ) -> EmploymentType:
        mapping = {
            "full time": EmploymentType.FULL_TIME,
            "full-time": EmploymentType.FULL_TIME,
            "part time": EmploymentType.PART_TIME,
            "part-time": EmploymentType.PART_TIME,
            "working student": EmploymentType.PART_TIME,
            "contract": EmploymentType.CONTRACT,
            "contractor": EmploymentType.CONTRACT,
            "freelance": EmploymentType.FREELANCE,
            "intern": EmploymentType.INTERNSHIP,
            "internship": EmploymentType.INTERNSHIP,
            "temporary": EmploymentType.TEMPORARY,
        }

        priority = (
            EmploymentType.FULL_TIME,
            EmploymentType.PART_TIME,
            EmploymentType.CONTRACT,
            EmploymentType.FREELANCE,
            EmploymentType.INTERNSHIP,
            EmploymentType.TEMPORARY,
        )

        normalized_values = {
            value.strip().casefold()
            for value in values
            if value.strip()
        }

        mapped_types = {
            mapping[value]
            for value in normalized_values
            if value in mapping
        }

        return next(
            (
                employment_type
                for employment_type in priority
                if employment_type in mapped_types
            ),
            EmploymentType.OTHER,
        )

    @staticmethod
    def _to_datetime(
        timestamp: int | float | None,
    ) -> datetime | None:
        if timestamp is None:
            return None

        return datetime.fromtimestamp(
            timestamp,
            tz=UTC,
        )