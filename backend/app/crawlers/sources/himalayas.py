from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.job import (
    CrawlPage,
    EmploymentType,
    JobCandidate,
    RawJob,
    SalaryPeriod,
    SeniorityLevel,
    WorkMode,
)
from app.utils.html import html_to_text

class HimalayasJob(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow"
    )

    title: str
    excerpt: str | None = None

    company_name: str = Field(alias="companyName")
    company_slug: str | None = Field(default=None, alias="companySlug")
    company_logo: str | None = Field(default=None, alias="companyLogo")

    employment_type: str | None = Field(default=None, alias="employmentType")
    location_restrictions: list[str] = Field(default_factory=list, alias="localtionRestriction")
    timezone_restriction: list[str] = Field(default_factory=list, alias="timezoneRestriction")
    
    category: list[str] = Field(default_factory=list)
    parent_categories: list[str] = Field(default_factory=list, alias="parentCategories")
    seniority: list[str] = Field(default_factory=list)

    min_salary: Decimal | None = Field(default=None, alias="minSalary")
    max_salary: Decimal | None = Field(default=None, alias="maxSalary")
    salary_period: str | None = Field(default=None, alias="salaryPeriod")
    currency: str | None = None

    description: str | None = None
    pub_date: int | float | None = Field(default=None, alias="pubDate")
    expiry_date: int | float | None = Field(default=None, alias="expiryDate")

    application_link: str = Field(alias="applicationLink")
    guid: str

    @field_validator(
        "location_restrictions",
        "timezone_restriction",
        "category",
        "parent_categories",
        "seniority",
        mode="before",
    )

    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        return list(value)

class HimalayasResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    jobs: list[HimalayasJob] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, alias="nextCursor")

class HimalayasJobSource:
    source_name = "himalayas"

    _API_URL = "https://himalayas.app/jobs/api"
    _MAX_LIMIT = 20

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_page(self, *, cursor: str | None = None, limit: int = 20) -> CrawlPage:
        if limit < 1:
            raise ValueError("limit must be greater than zero")

        params: dict[str, str | int] = {
            "limit": min(limit, self._MAX_LIMIT),
        }

        if cursor:
            params["cursor"] = cursor

        response = await self._client.get(self._API_URL, params=params)
        response.raise_for_status()

        page = HimalayasResponse.model_validate(response.json())

        raw_jobs = [
            RawJob(
                source=self.source_name,
                source_job_id=job.guid,
                source_url=job.application_link,
                payload=job.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=False,
                ),
            )
            for job in page.jobs
        ]

        return CrawlPage(items=raw_jobs, next_cursor=page.next_cursor)

    def map_to_candidate(self, raw_job: RawJob) -> JobCandidate:
        job = HimalayasJob.model_validate(raw_job.payload)

        description = html_to_text(job.description)
        if not description:
            description = job.excerpt or ""

        skills = list(
            dict.fromkeys(
                item.strip()
                for item in [
                    *job.category,
                    *job.parent_categories,
                ]
                if item.strip()
            )
        )

        location = ", ".join(job.location_restrictions)
        if not location:
            location = "Worldwide"

        return JobCandidate(
            source=self.source_name,
            source_job_id=job.guid,
            source_url=job.application_link,
            title=job.title,
            company=job.company_name,
            description=description,
            location=location,
            work_mode=WorkMode.REMOTE,
            employment_type=self._map_employment_type(job.employment_type),
            seniority_level=self._map_seniority(job.seniority),
            skills=skills,
            salary_min=job.min_salary,
            salary_max=job.max_salary,
            salary_currency=(
                job.currency.upper()
                if job.currency
                else None
            ),
            salary_period=self._map_salary_period(job.salary_period),
            posted_at=self._to_datetime(job.pub_date),
            expires_at=self._to_datetime(job.expiry_date),
            source_metadata={
                "company_slug": job.company_slug,
                "company_logo": job.company_logo,
                "timezone_restrictions": (
                    job.timezone_restriction
                ),
                "categories": job.category,
                "parent_categories": job.parent_categories,
                "excerpt": job.excerpt,
                "attribution": "Himalayas",
            },
        )

    @staticmethod
    def _map_employment_type(value: str | None) -> EmploymentType:
        mapping = {
            "full time": EmploymentType.FULL_TIME,
            "part time": EmploymentType.PART_TIME,
            "contractor": EmploymentType.CONTRACT,
            "temporary": EmploymentType.TEMPORARY,
            "intern": EmploymentType.INTERNSHIP,
        }

        normalized = (value or "").strip().lower()
        return mapping.get(normalized, EmploymentType.OTHER)

    @staticmethod
    def _map_salary_period(value: str | None) -> SalaryPeriod:
        mapping = {
            "hourly": SalaryPeriod.HOURLY,
            "weekly": SalaryPeriod.WEEKLY,
            "fortnightly": SalaryPeriod.FORTNIGHTLY,
            "monthly": SalaryPeriod.MONTHLY,
            "annual": SalaryPeriod.ANNUAL,
            "yearly": SalaryPeriod.ANNUAL,
        }

        normalized = (value or "").strip().lower()
        return mapping.get(normalized, SalaryPeriod.UNKNOWN)

    @staticmethod
    def _map_seniority(values: list[str]) -> SeniorityLevel:
        mapping = {
            "entry-level": SeniorityLevel.JUNIOR,
            "mid-level": SeniorityLevel.MIDDLE,
            "senior": SeniorityLevel.SENIOR,
            "manager": SeniorityLevel.MANAGER,
            "director": SeniorityLevel.DIRECTOR,
            "executive": SeniorityLevel.DIRECTOR,
        }

        priority = [
            SeniorityLevel.DIRECTOR,
            SeniorityLevel.MANAGER,
            SeniorityLevel.SENIOR,
            SeniorityLevel.MIDDLE,
            SeniorityLevel.JUNIOR,
        ]

        mapped = {
            mapping[value.strip().lower()]
            for value in values
            if value.strip().lower() in mapping
        }

        return next(
            (level for level in priority if level in mapped),
            SeniorityLevel.UNKNOWN,
        )

    @staticmethod
    def _to_datetime(timestamp: int | float | None) -> datetime | None:
        if timestamp is None:
            return None

        return datetime.fromtimestamp(timestamp, tz=UTC)
