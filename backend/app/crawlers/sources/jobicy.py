import re
from datetime import UTC, datetime
from decimal import Decimal
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
    SalaryPeriod,
    SeniorityLevel,
    WorkMode,
)
from app.utils.html import html_to_text


class JobicyJob(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    id: int | str
    url: str
    job_slug: str | None = Field(default=None, alias="jobSlug")
    job_title: str = Field(alias="jobTitle")
    company_name: str = Field(alias="companyName")
    company_logo: str | None = Field(default=None, alias="companyLogo")

    job_industry: list[str] = Field(default_factory=list, alias="jobIndustry")
    job_type: list[str] = Field(default_factory=list, alias="jobType")
    job_geo: str | None = Field(default=None, alias="jobGeo")
    job_level: str | None = Field(default=None, alias="jobLevel")
    job_excerpt: str | None = Field(default=None, alias="jobExcerpt")
    job_description: str | None = Field(default=None, alias="jobDescription")

    pub_date: datetime | None = Field(default=None, alias="pubDate")

    salary_min: Decimal | None = Field(default=None, alias="salaryMin", ge=0)
    salary_max: Decimal | None = Field(default=None, alias="salaryMax", ge=0)
    salary_currency: str | None = Field(default=None, alias="salaryCurrency")
    salary_period: str | None = Field(default=None, alias="salaryPeriod")

    @field_validator(
        "job_industry",
        "job_type",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        return list(value)


class JobicyResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobs: list[JobicyJob] = Field(default_factory=list)


class JobicyJobSource:
    source_name = "jobicy"

    _API_URL = "https://jobicy.com/api/v2/remote-jobs"
    _MAX_LIMIT = 100

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_page(self, *, cursor: str | None = None, limit: int = 20) -> CrawlPage:
        if cursor is not None:
            raise ValueError(
                "Jobicy does not support cursor pagination."
            )

        if limit < 1 or limit > self._MAX_LIMIT:
            raise ValueError(
                f"Jobicy limit must be between "
                f"1 and {self._MAX_LIMIT}."
            )

        response = await self._client.get(
            self._API_URL,
            params={"count": limit},
        )
        response.raise_for_status()

        page = JobicyResponse.model_validate(response.json())

        raw_jobs = [
            RawJob(
                source=self.source_name,
                source_job_id=str(job.id),
                source_url=job.url,
                payload=job.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=False,
                ),
            )
            for job in page.jobs
        ]

        return CrawlPage(
            items=raw_jobs,
            next_cursor=None,
        )

    def map_to_candidate(self, raw_job: RawJob) -> JobCandidate:
        job = JobicyJob.model_validate(raw_job.payload)
        description = html_to_text(job.job_description)

        if not description:
            description = job.job_excerpt or ""

        salary_min, salary_max, salary_currency = self._normalize_salary(job)

        return JobCandidate(
            source=self.source_name,
            source_job_id=str(job.id),
            source_url=job.url,
            title=job.job_title,
            company=job.company_name,
            description=description,
            location=job.job_geo or "Anywhere",
            employment_type=(
                self._map_employment_type(
                    job.job_type
                )
            ),
            work_mode=WorkMode.REMOTE,
            seniority_level=self._map_seniority(job.job_level),
            skills=job.job_industry,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_period=self._map_salary_period(job.salary_period),
            posted_at=self._to_utc(job.pub_date),
            source_metadata={
                "job_slug": job.job_slug,
                "company_logo": job.company_logo,
                "industries": job.job_industry,
                "job_types": job.job_type,
                "job_level": job.job_level,
                "excerpt": job.job_excerpt,
                "attribution": "Jobicy",
                "attribution_url": job.url,
            },
        )

    @staticmethod
    def _map_employment_type(values: list[str]) -> EmploymentType:
        mapping = {
            "full-time": EmploymentType.FULL_TIME,
            "full-time-permanent": EmploymentType.FULL_TIME,
            "part-time": EmploymentType.PART_TIME,
            "contract": EmploymentType.CONTRACT,
            "freelance": EmploymentType.FREELANCE,
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

        mapped_types = {
            mapping[JobicyJobSource._normalize_slug(value)]
            for value in values
            if JobicyJobSource._normalize_slug(value)
            in mapping
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
    def _map_seniority(value: str | None) -> SeniorityLevel:
        mapping = {
            "intern": SeniorityLevel.INTERN,
            "internship": SeniorityLevel.INTERN,
            "entry": SeniorityLevel.FRESHER,
            "entry-level": SeniorityLevel.FRESHER,
            "fresher": SeniorityLevel.FRESHER,
            "junior": SeniorityLevel.JUNIOR,
            "mid": SeniorityLevel.MIDDLE,
            "mid-level": SeniorityLevel.MIDDLE,
            "middle": SeniorityLevel.MIDDLE,
            "senior": SeniorityLevel.SENIOR,
            "lead": SeniorityLevel.LEAD,
            "manager": SeniorityLevel.MANAGER,
            "director": SeniorityLevel.DIRECTOR,
        }

        normalized = JobicyJobSource._normalize_slug(value or "")

        return mapping.get(
            normalized,
            SeniorityLevel.UNKNOWN,
        )

    @staticmethod
    def _map_salary_period(value: str | None) -> SalaryPeriod:
        mapping = {
            "hourly": SalaryPeriod.HOURLY,
            "weekly": SalaryPeriod.WEEKLY,
            "fortnightly": SalaryPeriod.FORTNIGHTLY,
            "monthly": SalaryPeriod.MONTHLY,
            "annual": SalaryPeriod.ANNUAL,
            "annually": SalaryPeriod.ANNUAL,
            "yearly": SalaryPeriod.ANNUAL,
        }

        normalized = JobicyJobSource._normalize_slug(
            value or ""
        )

        return mapping.get(
            normalized,
            SalaryPeriod.UNKNOWN,
        )

    @staticmethod
    def _normalize_salary(
        job: JobicyJob,
    ) -> tuple[
        Decimal | None,
        Decimal | None,
        str | None,
    ]:
        has_salary = (
            job.salary_min is not None
            or job.salary_max is not None
        )

        if not has_salary:
            return None, None, None

        currency = (
            job.salary_currency.strip().upper()
            if job.salary_currency
            else None
        )

        if (
            currency is None
            or len(currency) != 3
            or not currency.isalpha()
        ):
            return None, None, None

        return (
            job.salary_min,
            job.salary_max,
            currency,
        )

    @staticmethod
    def _normalize_slug(value: str) -> str:
        normalized = value.strip().casefold()
        normalized = re.sub(
            r"[\s_]+",
            "-",
            normalized,
        )

        return normalized

    @staticmethod
    def _to_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)