import json
from collections.abc import Callable

import httpx
import pytest
from app.crawlers.sources.itviec import ItViecJobSource
from app.crawlers.sources.structured_job_board import StructuredJobBoardSource
from app.crawlers.sources.topdev import TopDevJobSource
from app.schemas.job import (
    EmploymentType,
    SalaryPeriod,
    WorkMode,
)


def _detail_html(url: str) -> str:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": {"value": "job-123"},
        "url": url,
        "title": "Senior Python Developer",
        "description": "<p>Build reliable data services.</p>",
        "hiringOrganization": {"name": "Example Vietnam"},
        "employmentType": "FULL_TIME",
        "datePosted": "2026-08-24T08:00:00+07:00",
        "validThrough": "2026-09-24T23:59:59+07:00",
        "skills": "Python, SQL; Docker",
        "jobLocation": {
            "address": {
                "addressLocality": "Ho Chi Minh",
                "addressCountry": "VN",
            }
        },
        "baseSalary": {
            "currency": "VND",
            "value": {
                "minValue": 20_000_000,
                "maxValue": 30_000_000,
                "unitText": "MONTH",
            },
        },
    }

    return (
        '<script type="application/ld+json">'
        f"{json.dumps(posting)}"
        "</script>"
    )


@pytest.mark.parametrize(
    ("source_factory", "detail_url"),
    [
        (
            TopDevJobSource,
            "https://topdev.vn/viec-lam/python-developer-123",
        ),
        (
            ItViecJobSource,
            "https://itviec.com/it-jobs/python-developer-123",
        ),
    ],
)
@pytest.mark.asyncio
async def test_vietnam_source_fetches_and_maps_job_posting(
    source_factory: Callable[[httpx.AsyncClient], StructuredJobBoardSource],
    detail_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_html = f'<a href="{detail_url}?tracking=value">Job</a>'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {
            "/it-jobs",
            "/viec-lam/tim-kiem",
        }:
            return httpx.Response(200, text=listing_html, request=request)

        return httpx.Response(
            200,
            text=_detail_html(detail_url),
            request=request,
        )

    monkeypatch.setattr(
        StructuredJobBoardSource,
        "_REQUEST_DELAY_SECONDS",
        0,
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        source = source_factory(client)
        page = await source.fetch_page(cursor="2", limit=1)

    assert page.next_cursor == "3"
    assert len(page.items) == 1

    candidate = source.map_to_candidate(page.items[0])

    assert candidate.source_job_id == "job-123"
    assert candidate.title == "Senior Python Developer"
    assert candidate.company == "Example Vietnam"
    assert candidate.location == "Ho Chi Minh, VN"
    assert candidate.employment_type == EmploymentType.FULL_TIME
    assert candidate.work_mode == WorkMode.ONSITE
    assert candidate.salary_min == 20_000_000
    assert candidate.salary_max == 30_000_000
    assert candidate.salary_currency == "VND"
    assert candidate.salary_period == SalaryPeriod.MONTHLY
    assert candidate.skills == ["Python", "SQL", "Docker"]
