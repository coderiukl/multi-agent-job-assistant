"""Data-pipeline additions: skill taxonomy, category-aware mappers, the
PostgreSQL raw layer helpers and the raw re-processing logic (no database)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.cli.raw_jobs import normalize_raw_jobs, read_raw_jsonl
from app.crawlers.sources.himalayas import HimalayasJobSource
from app.crawlers.sources.jobicy import JobicyJobSource
from app.crawlers.sources.remotive import RemotiveJobSource
from app.normalizers.job import JobNormalizer
from app.normalizers.skills import (
    DEFAULT_TAXONOMY_PATH,
    MAX_SKILLS_PER_JOB,
    SkillTaxonomy,
    get_skill_taxonomy,
)
from app.repositories.composite_job import CompositeJobRepository
from app.repositories.postgres_raw_job import (
    PostgresRawJobRepository,
    build_payload_hash,
)
from app.schemas.job import JobCandidate, RawJob
from app.schemas.job_search import JobSearchFilters, JobSearchPlan, JobSearchRequest
from app.schemas.job_storage import JobUpsertSummary

TAXONOMY = get_skill_taxonomy()


def candidate(**overrides) -> JobCandidate:
    data = {
        "title": "Backend Engineer",
        "company": "Acme",
        "description": "Build services.",
        "source": "test",
        "source_job_id": "1",
        "source_url": "https://jobs.example.com/1",
    }
    data.update(overrides)
    return JobCandidate(**data)


# --------------------------------------------------------------------------
# Taxonomy
# --------------------------------------------------------------------------
def test_tax_01_taxonomy_file_is_consistent():
    """TC-TAX-01: the shipped taxonomy loads (no alias maps to two skills, no
    alias is also a category/ignored label) and has a version."""
    data = json.loads(DEFAULT_TAXONOMY_PATH.read_text(encoding="utf-8"))
    taxonomy = SkillTaxonomy(data)
    assert taxonomy.version == data["version"]
    assert len(taxonomy.skills) >= 150


def test_tax_02_conflicting_alias_is_rejected():
    data = {"version": "t", "skills": [
        {"name": "React", "aliases": ["reactjs"]},
        {"name": "Preact", "aliases": ["ReactJS"]}]}
    with pytest.raises(ValueError, match="maps to both"):
        SkillTaxonomy(data)
    with pytest.raises(ValueError, match="also a skill alias"):
        SkillTaxonomy({"version": "t", "skills": [{"name": "Sales"}],
                       "category_labels": ["sales"]})


@pytest.mark.parametrize(("label", "expected"), [
    ("ReactJS", "React"), ("react.js", "React"), ("PostgreSql", "PostgreSQL"),
    ("postgres", "PostgreSQL"), ("NodeJS", "Node.js"), ("Golang", "Go"),
    ("k8s", "Kubernetes"), (".Net Core", ".NET"), ("C#", "C#"), ("c++", "C++"),
    ("C language", "C"), ("QA QC", "Quality Assurance"), ("UI-UX", "UI/UX Design"),
    ("Japanese - N2", "Japanese"), ("Phyton", "Python"), ("GCP", "Google Cloud"),
])
def test_tax_03_labels_map_to_canonical_names(label, expected):
    assert TAXONOMY.canonical_name(label) == expected


def test_tax_04_labels_are_classified_as_skill_category_ignored_or_unmapped():
    """TC-TAX-04: categories move out of the skill list, noise is dropped,
    unknown labels stay (and are reported); HTML entities are unescaped."""
    result = TAXONOMY.normalize(
        ["ReactJS", "react", "Sales", "Customer Support &amp; Success", "Remote",
         "Berlin", "Fresher Accepted", "Quantum Basket Weaving", "PostgreSql"])
    assert result.skills == ["React", "PostgreSQL", "Quantum Basket Weaving"]
    assert result.categories == ["Sales", "Customer Support & Success"]
    assert result.unmapped == ["Quantum Basket Weaving"]


@pytest.mark.parametrize(("text", "present", "absent"), [
    ("Experience with Golang, Node.js and React Native.", {"Go", "Node.js", "React Native"}, set()),
    ("We use C++ and C# daily.", {"C++", "C#"}, {"C"}),
    ("Strong Java skills; JavaScript is a plus.", {"Java", "JavaScript"}, set()),
    ("ASP.NET Core and .NET 8 services", {"ASP.NET", ".NET"}, set()),
    ("You excel at communication and agile thinking in the spring.", set(),
     {"Excel", "Agile", "Spring", "Go"}),
    ("Advanced Excel and Agile ceremonies; Apache Spark jobs.", {"Excel", "Agile", "Apache Spark"}, set()),
    ("Let's go build a REST API on AWS with Docker.", {"REST API", "AWS", "Docker"}, {"Go"}),
    ("Node is fun", set(), {"Node.js"}),
])
def test_tax_05_text_extraction_is_conservative(text, present, absent):
    """TC-TAX-05: ambiguous words (go, excel, agile, spring, node, C) are only
    matched in unambiguous forms; symbols do not leak between C/C++/C#."""
    found = set(TAXONOMY.extract_from_text(text))
    assert present <= found
    assert not (absent & found)


def test_tax_06_source_skills_come_first_and_list_is_capped():
    text = " ".join(name for name in list(TAXONOMY.skills)[:120])
    result = TAXONOMY.normalize(["Kafka"], text=text)
    assert result.skills[0] == "Kafka"
    assert len(result.skills) == MAX_SKILLS_PER_JOB


def test_tax_07_query_skill_filter_moves_categories_to_keywords():
    skills, keywords = TAXONOMY.normalize_query_skills(
        ["reactjs", "Sales", "marketing", "Remote", "Some New Framework"])
    assert skills == ["React", "Some New Framework"]
    assert keywords == ["Sales", "marketing", "Remote"]


# --------------------------------------------------------------------------
# Normalizer
# --------------------------------------------------------------------------
def test_norm_01_normalizer_applies_taxonomy_and_records_metadata():
    job = JobNormalizer().normalize(candidate(
        skills=["ReactJS", "Sales"],
        description="Node.js services on Kubernetes.",
        source_metadata={"job_categories": ["Developer"]}))
    assert job.skills == ["React", "Node.js", "Kubernetes"]
    assert job.source_metadata["job_categories"] == ["Developer", "Sales"]
    assert job.source_metadata["raw_skills"] == ["ReactJS", "Sales"]
    assert job.source_metadata["skill_taxonomy_version"] == TAXONOMY.version


def test_norm_02_taxonomy_version_is_part_of_the_content_hash():
    """TC-NORM-02: a taxonomy change re-writes jobs (hash changes) even when
    the mapped skills stay the same; the same version is deterministic."""
    data = json.loads(DEFAULT_TAXONOMY_PATH.read_text(encoding="utf-8"))
    bumped = SkillTaxonomy({**data, "version": data["version"] + "-next"})
    base = candidate(skills=["Python"])
    first = JobNormalizer().normalize(base)
    assert JobNormalizer().normalize(base).content_hash == first.content_hash
    assert JobNormalizer(bumped).normalize(base).content_hash != first.content_hash
    assert JobNormalizer(bumped).normalize(base).job_id == first.job_id


def test_norm_03_normalizing_twice_is_stable():
    once = JobNormalizer().normalize(candidate(skills=["ReactJS", "Sales"]))
    again = JobNormalizer().normalize(JobCandidate.model_validate(
        once.model_dump(exclude={"job_id", "content_hash"})))
    assert again.skills == once.skills
    assert again.content_hash == once.content_hash


# --------------------------------------------------------------------------
# Mappers: category fields are not skills
# --------------------------------------------------------------------------
def _raw(source: str, payload: dict, job_id: str = "42") -> RawJob:
    return RawJob(source=source, source_job_id=job_id,
                  source_url="https://jobs.example.com/42", payload=payload)


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(500))) as client:
        yield client


async def test_map_01_remotive_category_is_a_job_category(http_client):
    raw = _raw("remotive", {
        "id": 42, "url": "https://remotive.com/42", "title": "Senior Golang Engineer",
        "company_name": "Acme", "category": "Software Development",
        "description": "<p>Go services with PostgreSQL and Kafka.</p>"})
    job = JobNormalizer().normalize(RemotiveJobSource(http_client).map_to_candidate(raw))
    assert "Software Development" not in job.skills
    assert job.source_metadata["job_categories"] == ["Software Development"]
    assert {"Go", "PostgreSQL", "Kafka"} <= set(job.skills)


async def test_map_02_jobicy_industries_are_job_categories(http_client):
    raw = _raw("jobicy", {
        "id": 42, "url": "https://jobicy.com/42", "jobTitle": "Data Engineer",
        "companyName": "Acme", "jobIndustry": ["Data Science &amp; Analytics"],
        "jobDescription": "Airflow, dbt and Snowflake pipelines in Python."})
    job = JobNormalizer().normalize(JobicyJobSource(http_client).map_to_candidate(raw))
    assert job.source_metadata["job_categories"] == ["Data Science & Analytics"]
    assert {"Airflow", "dbt", "Snowflake", "Python"} <= set(job.skills)
    assert all("Analytics" not in skill for skill in job.skills)


async def test_map_03_himalayas_categories_are_job_categories(http_client):
    raw = _raw("himalayas", {
        "title": "Backend Developer", "companyName": "Acme", "applicationLink":
        "https://himalayas.app/42", "guid": "42", "category": ["Developer"],
        "parentCategories": ["Software Engineering"],
        "description": "Django and React on AWS."})
    job = JobNormalizer().normalize(HimalayasJobSource(http_client).map_to_candidate(raw))
    assert job.source_metadata["job_categories"] == ["Developer", "Software Engineering"]
    assert set(job.skills) == {"Django", "React", "AWS"}


# --------------------------------------------------------------------------
# Raw layer helpers
# --------------------------------------------------------------------------
def test_raw_01_rows_are_deduplicated_hashed_and_nul_free():
    crawled = datetime(2026, 11, 1, tzinfo=UTC)
    jobs = [
        RawJob(source="Remotive", source_job_id="1", source_url="https://x.example/1",
               payload={"b": 1, "a": "x\x00y"}, crawled_at=crawled),
        RawJob(source="remotive", source_job_id="1", source_url="https://x.example/1",
               payload={"a": "x\x00y", "b": 1}, crawled_at=crawled),
        RawJob(source="remotive", source_job_id="1", source_url="https://x.example/1",
               payload={"a": "changed", "b": 1}, crawled_at=crawled),
    ]
    rows = PostgresRawJobRepository._build_rows(batch_id="b1", jobs=jobs)
    assert len(rows) == 2  # identical payloads (key order irrelevant) collapse
    assert rows[0]["source"] == "remotive"
    assert rows[0]["payload"] == {"b": 1, "a": "xy"}
    assert rows[0]["payload_hash"] == build_payload_hash({"a": "xy", "b": 1})
    assert rows[0]["payload_hash"] != rows[1]["payload_hash"]


def test_raw_02_read_raw_jsonl_skips_invalid_lines(tmp_path: Path):
    path = tmp_path / "batch.jsonl"
    valid = RawJob(source="remotive", source_job_id="1",
                   source_url="https://x.example/1", payload={"a": 1})
    path.write_text(valid.model_dump_json() + "\n\n{not json}\n", encoding="utf-8")
    jobs, invalid = read_raw_jsonl(path)
    assert [job.source_job_id for job in jobs] == ["1"]
    assert invalid == 1


class RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def save_raw_records(self, *, batch_id, jobs):
        self.calls.append((batch_id, len(jobs)))
        return len(jobs)


class FileRepo:
    async def save_raw_batch(self, *, source, batch_id, jobs):
        return Path(f"/raw/{source}/{batch_id}.jsonl")

    async def upsert_many(self, jobs):
        return JobUpsertSummary()


async def test_raw_03_composite_writes_jsonl_and_postgres_raw():
    store = RecordingStore()
    repo = CompositeJobRepository(raw_repository=FileRepo(), normalized_repository=FileRepo(),
                                  raw_record_store=store)
    raw = RawJob(source="remotive", source_job_id="1", source_url="https://x.example/1",
                 payload={})
    path = await repo.save_raw_batch(source="remotive", batch_id="b1", jobs=[raw])
    assert path == Path("/raw/remotive/b1.jsonl")
    assert store.calls == [("b1", 1)]


async def test_raw_04_reprocessing_maps_normalizes_and_counts_failures(http_client):
    good = _raw("remotive", {"id": 1, "url": "https://remotive.com/1", "title": "Python Dev",
                             "company_name": "Acme", "description": "Python and FastAPI"}, "1")
    bad = _raw("remotive", {"id": 2, "url": "https://remotive.com/2"}, "2")  # no title
    sources = {"remotive": RemotiveJobSource(http_client)}
    jobs, failures = normalize_raw_jobs(raw_jobs=[good, bad], source_for=sources.__getitem__,
                                        normalizer=JobNormalizer())
    assert [job.source_job_id for job in jobs] == ["1"]
    assert {"Python", "FastAPI"} <= set(jobs[0].skills)
    assert failures == Counter({"ValidationError": 1})


# --------------------------------------------------------------------------
# Query side
# --------------------------------------------------------------------------
def test_query_01_planner_skill_filter_is_canonicalized():
    from app.agents.job_search_agent import JobSearchAgent

    plan = JobSearchPlan(original_query="q", semantic_query="sales react jobs",
                         keywords=["jobs"],
                         filters=JobSearchFilters(skills=["reactjs", "Sales"]))
    result = JobSearchAgent._apply_request_constraints(
        request=JobSearchRequest(query="q"), plan=plan)
    assert result.filters.skills == ["React"]
    assert result.keywords == ["jobs", "Sales"]


# --------------------------------------------------------------------------
# Airflow: dbt analytics DAG
# --------------------------------------------------------------------------
def test_dag_01_dbt_analytics_dag_wiring():
    """TC-DAG-01: freshness check gates dbt build; dbt runs from its own
    virtualenv and writes target/logs outside the read-only project mount."""
    pytest.importorskip("airflow.sdk")
    import sys

    dags_dir = Path(__file__).resolve().parents[3] / "airflow" / "dags"
    sys.path.insert(0, str(dags_dir))
    import job_analytics_dag

    dag = job_analytics_dag.job_analytics_dbt()
    assert set(dag.task_ids) == {"dbt_source_freshness", "dbt_build"}
    assert dag.get_task("dbt_build").upstream_task_ids == {"dbt_source_freshness"}
    assert dag.max_active_runs == 1 and dag.catchup is False
    command = job_analytics_dag.dbt_command("build")
    assert command.startswith("/opt/dbt_venv/bin/dbt build ")
    assert "--target-path /tmp/dbt/target" in command
