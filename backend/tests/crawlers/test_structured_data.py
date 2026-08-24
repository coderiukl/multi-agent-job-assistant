import json

from app.crawlers.structured_data import extract_job_posting, extract_links


def test_extract_links_filters_host_path_and_duplicates() -> None:
    html = """
    <a href="/it-jobs/python-developer-123?tracking=one">Job</a>
    <a href="/it-jobs/python-developer-123?tracking=two">Duplicate</a>
    <a href="https://example.com/it-jobs/ignored-999">External</a>
    <a href="/companies/company-name">Company</a>
    """

    links = extract_links(
        html,
        base_url="https://itviec.com/it-jobs?page=1",
        allowed_hosts=frozenset({"itviec.com"}),
        path_prefix="/it-jobs/",
    )

    assert links == [
        "https://itviec.com/it-jobs/python-developer-123"
    ]


def test_extract_job_posting_from_json_ld_graph() -> None:
    posting = {
        "@type": "JobPosting",
        "title": "Data Engineer",
    }
    document = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": "ITviec"},
            posting,
        ],
    }
    html = (
        '<script type="application/ld+json">'
        f"{json.dumps(document)}"
        "</script>"
    )

    assert extract_job_posting(html) == posting


def test_extract_job_posting_ignores_invalid_json_ld() -> None:
    html = """
    <script type="application/ld+json">not-json</script>
    <script type="application/ld+json">
      {"@type": "JobPosting", "title": "Backend Developer"}
    </script>
    """

    posting = extract_job_posting(html)

    assert posting is not None
    assert posting["title"] == "Backend Developer"
