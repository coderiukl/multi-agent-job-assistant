import asyncio
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from app.crawlers.structured_data import extract_job_posting, extract_links
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

LOGGER = logging.getLogger(__name__)


class StructuredJobBoardSource:
    source_name: ClassVar[str]
    attribution: ClassVar[str]
    listing_url: ClassVar[str]
    detail_path_prefix: ClassVar[str]
    detail_path_pattern: ClassVar[str]
    allowed_hosts: ClassVar[frozenset[str]]

    _MAX_LIMIT = 20
    _REQUEST_DELAY_SECONDS = 0.3
    _HTML_HEADERS: ClassVar[dict[str, str]] = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "vi,en;q=0.8",
    }

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_page(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CrawlPage:
        if limit < 1 or limit > self._MAX_LIMIT:
            raise ValueError(
                f"{self.attribution} limit must be between "
                f"1 and {self._MAX_LIMIT}."
            )

        page_number = self._parse_cursor(cursor)
        listing_response = await self._client.get(
            self.listing_url,
            params={"page": page_number},
            headers=self._HTML_HEADERS,
        )
        listing_response.raise_for_status()

        detail_urls = [
            url
            for url in extract_links(
                listing_response.text,
                base_url=str(listing_response.url),
                allowed_hosts=self.allowed_hosts,
                path_prefix=self.detail_path_prefix,
            )
            if re.fullmatch(
                self.detail_path_pattern,
                urlsplit(url).path,
            )
        ][:limit]

        raw_jobs: list[RawJob] = []

        for index, detail_url in enumerate(detail_urls):
            try:
                detail_response = await self._client.get(
                    detail_url,
                    headers=self._HTML_HEADERS,
                )
                detail_response.raise_for_status()
            except httpx.HTTPError:
                LOGGER.warning(
                    "Could not fetch job detail from %s",
                    detail_url,
                    exc_info=True,
                )
                continue

            posting = extract_job_posting(detail_response.text)

            if posting is None:
                LOGGER.warning(
                    "No JobPosting structured data found at %s",
                    detail_url,
                )
                continue

            canonical_url = self._canonical_url(
                posting.get("url"),
                fallback=detail_url,
            )
            source_job_id = self._source_job_id(posting, canonical_url)
            payload = {
                **posting,
                "_canonical_url": canonical_url,
            }

            raw_jobs.append(
                RawJob(
                    source=self.source_name,
                    source_job_id=source_job_id,
                    source_url=canonical_url,
                    payload=payload,
                )
            )

            if (
                self._REQUEST_DELAY_SECONDS > 0
                and index < len(detail_urls) - 1
            ):
                await asyncio.sleep(self._REQUEST_DELAY_SECONDS)

        next_cursor = (
            str(page_number + 1)
            if len(detail_urls) == limit
            else None
        )

        return CrawlPage(items=raw_jobs, next_cursor=next_cursor)

    def map_to_candidate(self, raw_job: RawJob) -> JobCandidate:
        posting = raw_job.payload
        description = html_to_text(self._text(posting.get("description")))

        if not description:
            description = html_to_text(
                self._text(posting.get("responsibilities"))
                or self._text(posting.get("qualifications"))
            )

        salary_min, salary_max, currency, salary_period = self._salary(
            posting.get("baseSalary")
        )
        title = self._text(posting.get("title"))
        company = self._organization_name(
            posting.get("hiringOrganization")
        )
        location = self._location(posting)

        return JobCandidate(
            source=self.source_name,
            source_job_id=raw_job.source_job_id,
            source_url=raw_job.source_url,
            title=title,
            company=company,
            description=description,
            location=location,
            employment_type=self._employment_type(
                posting.get("employmentType")
            ),
            work_mode=self._work_mode(posting, title),
            seniority_level=self._seniority(posting, title),
            skills=self._skills(posting),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period=salary_period,
            posted_at=self._datetime(posting.get("datePosted")),
            expires_at=self._datetime(posting.get("validThrough")),
            source_metadata={
                "identifier": posting.get("identifier"),
                "industry": posting.get("industry"),
                "job_location_type": posting.get("jobLocationType"),
                "attribution": self.attribution,
                "attribution_url": str(raw_job.source_url),
            },
        )

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None or not cursor.strip():
            return 1

        try:
            page_number = int(cursor.strip())
        except ValueError as error:
            raise ValueError("Cursor must be a positive page number.") from error

        if page_number < 1:
            raise ValueError("Cursor must be a positive page number.")

        return page_number

    @staticmethod
    def _source_job_id(posting: dict[str, Any], url: str) -> str:
        identifier = posting.get("identifier")

        if isinstance(identifier, dict):
            value = identifier.get("value") or identifier.get("name")
        else:
            value = identifier

        normalized = StructuredJobBoardSource._text(value)

        if normalized:
            return normalized[:255]

        path = urlsplit(url).path.rstrip("/")
        numeric_id = re.search(r"(\d+)(?:\.html)?$", path)

        if numeric_id:
            return numeric_id.group(1)

        slug = path.rsplit("/", maxsplit=1)[-1]

        if not slug:
            raise ValueError("Could not determine source job id.")

        return slug[:255]

    def _canonical_url(self, value: Any, *, fallback: str) -> str:
        candidate = urljoin(fallback, self._text(value))
        parsed = urlsplit(candidate)

        if parsed.hostname not in self.allowed_hosts:
            parsed = urlsplit(fallback)

        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, dict):
            return StructuredJobBoardSource._text(
                value.get("name") or value.get("value")
            )

        if isinstance(value, list):
            return ", ".join(
                text
                for item in value
                if (text := StructuredJobBoardSource._text(item))
            )

        return str(value).strip()

    @staticmethod
    def _organization_name(value: Any) -> str:
        return StructuredJobBoardSource._text(value)

    @staticmethod
    def _employment_type(value: Any) -> EmploymentType:
        mapping = {
            "fulltime": EmploymentType.FULL_TIME,
            "full-time": EmploymentType.FULL_TIME,
            "parttime": EmploymentType.PART_TIME,
            "part-time": EmploymentType.PART_TIME,
            "contractor": EmploymentType.CONTRACT,
            "contract": EmploymentType.CONTRACT,
            "temporary": EmploymentType.TEMPORARY,
            "internship": EmploymentType.INTERNSHIP,
            "intern": EmploymentType.INTERNSHIP,
            "freelance": EmploymentType.FREELANCE,
        }
        values = value if isinstance(value, list) else [value]

        for item in values:
            normalized = re.sub(
                r"[\s_]",
                "",
                StructuredJobBoardSource._text(item).casefold(),
            )

            if normalized in mapping:
                return mapping[normalized]

        return EmploymentType.OTHER

    @staticmethod
    def _work_mode(posting: dict[str, Any], title: str) -> WorkMode:
        location_type = StructuredJobBoardSource._text(
            posting.get("jobLocationType")
        ).casefold()
        title_text = title.casefold()

        if "telecommute" in location_type or "remote" in title_text:
            return WorkMode.REMOTE

        description = StructuredJobBoardSource._text(
            posting.get("description")
        ).casefold()

        if "hybrid" in description or "kết hợp" in description:
            return WorkMode.HYBRID

        if posting.get("jobLocation"):
            return WorkMode.ONSITE

        return WorkMode.UNKNOWN

    @staticmethod
    def _seniority(
        posting: dict[str, Any],
        title: str,
    ) -> SeniorityLevel:
        text = " ".join(
            [
                title,
                StructuredJobBoardSource._text(
                    posting.get("experienceRequirements")
                ),
            ]
        ).casefold()
        mapping = (
            ("director", SeniorityLevel.DIRECTOR),
            ("manager", SeniorityLevel.MANAGER),
            ("lead", SeniorityLevel.LEAD),
            ("senior", SeniorityLevel.SENIOR),
            ("middle", SeniorityLevel.MIDDLE),
            ("mid-level", SeniorityLevel.MIDDLE),
            ("junior", SeniorityLevel.JUNIOR),
            ("fresher", SeniorityLevel.FRESHER),
            ("intern", SeniorityLevel.INTERN),
        )

        return next(
            (level for keyword, level in mapping if keyword in text),
            SeniorityLevel.UNKNOWN,
        )

    @staticmethod
    def _skills(posting: dict[str, Any]) -> list[str]:
        values = [
            posting.get("skills"),
            posting.get("occupationalCategory"),
        ]
        skills: list[str] = []

        for value in values:
            items = value if isinstance(value, list) else [value]

            for item in items:
                text = StructuredJobBoardSource._text(item)

                if not text:
                    continue

                skills.extend(
                    part.strip()
                    for part in re.split(r"[,;|]", text)
                    if part.strip()
                )

        return list(dict.fromkeys(skills))

    @staticmethod
    def _location(posting: dict[str, Any]) -> str:
        if "telecommute" in StructuredJobBoardSource._text(
            posting.get("jobLocationType")
        ).casefold():
            return "Remote"

        locations = posting.get("jobLocation")
        locations = locations if isinstance(locations, list) else [locations]
        names: list[str] = []

        for location in locations:
            if not isinstance(location, dict):
                text = StructuredJobBoardSource._text(location)
            else:
                address = location.get("address", location)

                if isinstance(address, dict):
                    parts = [
                        StructuredJobBoardSource._text(
                            address.get(field)
                        )
                        for field in (
                            "addressLocality",
                            "addressRegion",
                            "addressCountry",
                        )
                    ]
                    text = ", ".join(
                        dict.fromkeys(part for part in parts if part)
                    )
                else:
                    text = StructuredJobBoardSource._text(address)

            if text and text not in names:
                names.append(text)

        if names:
            return " | ".join(names)

        return StructuredJobBoardSource._text(
            posting.get("applicantLocationRequirements")
        ) or "Việt Nam"

    @staticmethod
    def _salary(
        value: Any,
    ) -> tuple[
        Decimal | None,
        Decimal | None,
        str | None,
        SalaryPeriod,
    ]:
        if not isinstance(value, dict):
            return None, None, None, SalaryPeriod.UNKNOWN

        currency = StructuredJobBoardSource._text(
            value.get("currency")
        ).upper()
        salary_value = value.get("value", value)

        if not isinstance(salary_value, dict):
            salary_value = {"value": salary_value}

        minimum = StructuredJobBoardSource._decimal(
            salary_value.get("minValue") or salary_value.get("value")
        )
        maximum = StructuredJobBoardSource._decimal(
            salary_value.get("maxValue") or salary_value.get("value")
        )

        if minimum is None and maximum is None:
            return None, None, None, SalaryPeriod.UNKNOWN

        if len(currency) != 3 or not currency.isalpha():
            return None, None, None, SalaryPeriod.UNKNOWN

        unit = StructuredJobBoardSource._text(
            salary_value.get("unitText")
        ).casefold()
        period_mapping = {
            "hour": SalaryPeriod.HOURLY,
            "week": SalaryPeriod.WEEKLY,
            "month": SalaryPeriod.MONTHLY,
            "year": SalaryPeriod.ANNUAL,
        }
        period = next(
            (
                mapped
                for keyword, mapped in period_mapping.items()
                if keyword in unit
            ),
            SalaryPeriod.UNKNOWN,
        )

        return minimum, maximum, currency, period

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            number = Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return None

        return number if number >= 0 else None

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        text = StructuredJobBoardSource._text(value)

        if not text:
            return None

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC)
