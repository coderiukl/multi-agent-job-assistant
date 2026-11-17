"""Data pipeline tests (Phase 4 – Airflow / crawl / normalize / dedup).

Crawlers are driven with httpx.MockTransport (no network). The Airflow DAG
module is imported directly to test its quality gate without a scheduler."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

from app.crawlers.sources.arbeitnow import ArbeitnowJobSource
from app.normalizers.job import JobNormalizer
from app.utils.html import html_to_text
from app.utils.job_deduplication import build_job_deduplication_key
from tests.conftest import make_job

DAGS = Path(__file__).resolve().parents[3] / "airflow" / "dags"


def arbeitnow_page(count: int, *, page: int = 1, has_next: bool = True) -> dict:
    return {
        "data": [{"slug": f"job-{page}-{i}", "company_name": "Acme", "title": f"Dev {i}",
                  "description": "<p>Python <b>dev</b></p>", "remote": True,
                  "url": f"https://www.arbeitnow.com/jobs/{page}-{i}", "tags": ["python"],
                  "job_types": ["full time"], "location": "Berlin",
                  "created_at": 1_760_000_000} for i in range(count)],
        "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=2" if has_next else None},
        "meta": {"current_page": page, "last_page": None},
    }


def source(payload: dict) -> ArbeitnowJobSource:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    return ArbeitnowJobSource(client=httpx.AsyncClient(transport=transport))


async def test_pipe_01_arbeitnow_does_not_skip_jobs_on_a_page():
    """TC-PIPE-01 (BUG-022 fixed): a 100-job page crawled with limit=20 keeps
    the position inside the page in the cursor; five runs read every job of
    the page exactly once, then the cursor moves to the next page."""
    crawler = source(arbeitnow_page(100))
    cursor, seen = "1", []
    for _ in range(5):
        page = await crawler.fetch_page(cursor=cursor, limit=20)
        seen.extend(item.source_job_id for item in page.items)
        cursor = page.next_cursor
    assert seen == [f"job-1-{i}" for i in range(100)]
    assert cursor == "2"


async def test_pipe_01b_legacy_and_offset_cursors():
    """TC-PIPE-01b: the stored legacy cursor ("56") still works; a page shorter
    than the limit ends on the next page / None; bad cursors are rejected."""
    crawler = source(arbeitnow_page(30, page=56, has_next=False))
    first = await crawler.fetch_page(cursor="56", limit=20)
    assert (len(first.items), first.next_cursor) == (20, "56:20")
    rest = await crawler.fetch_page(cursor=first.next_cursor, limit=20)
    assert (len(rest.items), rest.next_cursor) == (10, None)
    for bad in ("0", "x", "2:-1", "2:y"):
        with pytest.raises(ValueError):
            await crawler.fetch_page(cursor=bad)


async def test_pipe_02_arbeitnow_exhausted_cursor_returns_nothing():
    """TC-PIPE-02: past the last page the source returns 0 items, no cursor."""
    page = await source(arbeitnow_page(0, page=56, has_next=False)).fetch_page(cursor="56")
    assert (page.items, page.next_cursor) == ([], None)


@pytest.fixture(scope="module")
def dag_module():
    pytest.importorskip("airflow.sdk")
    sys.path.insert(0, str(DAGS))
    import job_crawling_dag

    return job_crawling_dag


def metrics(tmp_path, **overrides):
    raw = tmp_path / "raw.jsonl"
    raw.write_text("{}\n")
    base = {"source": "s", "batch_id": "b", "fetched_count": 20, "normalized_count": 20,
            "failed_count": 0, "inserted_count": 5, "updated_count": 0,
            "unchanged_count": 15, "raw_file_path": str(raw), "normalized_job_ids": [],
            "current_cursor": "55", "next_cursor": "56"}
    return {**base, **overrides}


def test_pipe_03_quality_gate_accepts_healthy_batch(dag_module, tmp_path):
    """TC-PIPE-03: a complete batch passes and reports duplicates/failure rate."""
    result = dag_module._validate_metrics(metrics(tmp_path), expected_limit=20,
                                          min_fetch_ratio=0.8, min_fetch_count=1)
    assert result["quality_status"] == "passed" and result["failure_rate"] == 0


@pytest.mark.parametrize("override", [
    {"failed_count": 5, "normalized_count": 15},         # 25 % failures
    {"normalized_count": 19},                            # totals inconsistent
    {"inserted_count": 0, "unchanged_count": 0},         # nothing written
])
def test_pipe_04_quality_gate_rejects_bad_batches(dag_module, tmp_path, override):
    """TC-PIPE-04: high failure rate / inconsistent counters are rejected."""
    with pytest.raises(ValueError):
        dag_module._validate_metrics(metrics(tmp_path, **override), expected_limit=20,
                                     min_fetch_ratio=0.8, min_fetch_count=1)


def test_pipe_05_exhausted_cursor_does_not_fail_forever(dag_module, tmp_path):
    """TC-PIPE-05 (BUG-023 fixed): when the source is exhausted (0 items,
    next_cursor None after a stored cursor) the run succeeds with
    quality_status=source_exhausted, so commit_source_cursor stores "" and the
    next run restarts from page 1 (observed live: cursor stuck at 56)."""
    exhausted = metrics(tmp_path, fetched_count=0, normalized_count=0, inserted_count=0,
                        unchanged_count=0, next_cursor=None)
    (tmp_path / "raw.jsonl").write_text("")  # an empty batch has an empty raw file
    result = dag_module._validate_metrics(exhausted, expected_limit=20, min_fetch_ratio=0.8,
                                          min_fetch_count=1)
    assert result["quality_status"] == "source_exhausted"
    assert result["next_cursor"] is None


@pytest.mark.parametrize("override", [
    {"current_cursor": None, "next_cursor": None},   # empty FIRST page: source broken
    {"next_cursor": "57"},                            # empty page but more pages exist
])
def test_pipe_05b_empty_batches_that_are_not_exhaustion_still_fail(dag_module, tmp_path,
                                                                   override):
    """TC-PIPE-05b: the exhaustion rule does not weaken the gate – an empty
    first page or an empty middle page still fails the run."""
    empty = metrics(tmp_path, fetched_count=0, normalized_count=0, inserted_count=0,
                    unchanged_count=0, **override)
    with pytest.raises(ValueError, match="below the required minimum"):
        dag_module._validate_metrics(empty, expected_limit=20, min_fetch_ratio=0.8,
                                     min_fetch_count=1)


def test_pipe_06_dag_wiring(dag_module):
    """TC-PIPE-06 (BUG-023 fixed): index_jobs depends only on the crawl, so rows
    already written to PostgreSQL are indexed even if the quality gate fails;
    cursor commit still requires a passing gate."""
    dag = dag_module.job_crawl_arbeitnow
    index = dag.get_task("index_jobs")
    assert index.upstream_task_ids == {"crawl_arbeitnow_jobs"}
    assert dag.get_task("commit_source_cursor").upstream_task_ids == {"validate_crawl_quality"}
    assert dag.get_task("crawl_arbeitnow_jobs").retries == 3
    assert dag.max_active_runs == 1 and dag.catchup is False


def test_pipe_06b_index_ids_come_from_the_crawl(dag_module, tmp_path):
    """TC-PIPE-06b: the index task indexes exactly the IDs the crawl wrote."""
    assert dag_module._index_job_ids(metrics(tmp_path, normalized_job_ids=["a", "b"])) == [
        "a", "b"]
    assert dag_module._index_job_ids(metrics(tmp_path, normalized_job_ids=None)) == []


def test_pipe_07_normalizer_is_deterministic():
    """TC-PIPE-07: job_id from (source, source_job_id); crawl time not hashed."""
    from datetime import UTC, datetime

    first = make_job(1, posted_days_ago=None, crawled_at=datetime(2026, 1, 1, tzinfo=UTC))
    second = make_job(1, posted_days_ago=None, crawled_at=datetime(2026, 2, 1, tzinfo=UTC))
    # crawl time differs but is not part of the content hash
    assert (first.job_id, first.content_hash) == (second.job_id, second.content_hash)
    changed = make_job(1, description="different", posted_days_ago=None)
    assert changed.job_id == first.job_id and changed.content_hash != first.content_hash
    assert len(JobNormalizer._build_job_id(first)) == 64


def test_pipe_08_dedup_key_normalises_locations_and_accents():
    """TC-PIPE-08: 'TP.HCM' == 'Ho Chi Minh City'; accents/case ignored."""
    a = make_job(1, title="Lập trình viên Python", company="ACME", location="TP.HCM")
    b = make_job(2, title="lap trinh vien python", company="acme", location="Ho Chi Minh City")
    assert build_job_deduplication_key(a) == build_job_deduplication_key(b)


def test_pipe_09_html_is_converted_to_text():
    """TC-PIPE-09: block tags become line breaks, inline tags are removed."""
    assert html_to_text("<p>Python <b>dev</b></p><ul><li>SQL</li></ul>") == "Python dev\nSQL"


@pytest.mark.parametrize("raw", ["<p>Python</p><script>alert(1)</script><style>p{}</style>",
                                 "&lt;p&gt;Python&lt;/p&gt;",
                                 "&lt;p&gt;Python&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;"])
def test_pipe_10_no_markup_or_code_left_in_descriptions(raw):
    """TC-PIPE-10 (BUG-024 fixed): descriptions fed to embeddings/LLM contain
    neither script/style bodies nor literal tags."""
    text = html_to_text(raw)
    assert text == "Python"


@pytest.mark.parametrize(("raw", "expected"), [
    ("Salary &lt; 2000 USD and C++ &amp; Go", "Salary < 2000 USD and C++ & Go"),
    ("<p>Use a &lt;= b</p>", "Use a <= b"),
    ("I <3 Python", "I <3 Python"),
])
def test_pipe_10b_real_text_with_angle_brackets_survives(raw, expected):
    """TC-PIPE-10b: only escaped *markup* is re-parsed; comparison signs and
    entities in ordinary text are kept."""
    assert html_to_text(raw) == expected
