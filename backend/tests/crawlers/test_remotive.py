import httpx
import pytest
from app.crawlers.sources.remotive import RemotiveJobSource
from app.schemas.job import EmploymentType


@pytest.mark.asyncio
async def test_remotive_source_serializes_and_maps_employment_type() -> None:
    payload = {
        "job-count": 1,
        "jobs": [
            {
                "id": 123,
                "url": "https://remotive.com/remote-jobs/software-dev/test-123",
                "title": "Backend Engineer",
                "company_name": "Example",
                "job_type": "full_time",
                "description": "<p>Build APIs.</p>",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        source = RemotiveJobSource(client)
        page = await source.fetch_page(limit=1)

    candidate = source.map_to_candidate(page.items[0])

    assert candidate.employment_type == EmploymentType.FULL_TIME
    assert candidate.description == "Build APIs."
