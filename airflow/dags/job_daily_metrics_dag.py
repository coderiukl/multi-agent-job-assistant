from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow.sdk import Variable, dag, get_current_context, task
from common.callbacks import persist_failure_alert

LOGGER = logging.getLogger(__name__)

LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
DATA_DIRECTORY = Path("/opt/airflow/data/jobs")
METRICS_DIRECTORY = DATA_DIRECTORY / "metrics"
DAILY_METRICS_DIRECTORY = METRICS_DIRECTORY / "daily"

SOURCES_VARIABLE = "job_metrics_sources"
FRESHNESS_HOURS_VARIABLE = "job_no_new_data_hours"
MIN_DAILY_FETCHED_VARIABLE = "job_daily_min_fetched"
MAX_DAILY_FETCHED_VARIABLE = "job_daily_max_fetched"

DEFAULT_SOURCES = (
    "himalayas",
    "remotive",
    "jobicy",
    "arbeitnow",
    "topdev",
    "itviec",
)
DEFAULT_FRESHNESS_HOURS = 24
DEFAULT_MIN_DAILY_FETCHED = 150
DEFAULT_MAX_DAILY_FETCHED = 200
PLANNED_DAILY_FETCHED = 175

COUNT_FIELDS = (
    "fetched_count",
    "normalized_count",
    "failed_count",
    "inserted_count",
    "updated_count",
    "unchanged_count",
)


def _positive_int_variable(name: str, default: int) -> int:
    raw_value = Variable.get(name, default=str(default))

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error

    if value < 1:
        raise ValueError(f"{name} must be greater than zero")

    return value


def _parse_sources(raw_value: Any) -> list[str]:
    values = str(raw_value).split(",")
    sources = list(
        dict.fromkeys(
            value.strip().casefold()
            for value in values
            if value.strip()
        )
    )

    if not sources:
        raise ValueError("At least one metrics source is required")

    unsupported = set(sources) - set(DEFAULT_SOURCES)

    if unsupported:
        raise ValueError(
            "Unsupported metrics sources: "
            + ", ".join(sorted(unsupported))
        )

    return sources


def _load_json_record(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read metrics file: {path}") from error

    if not isinstance(data, dict):
        raise TypeError(f"Metrics file must contain an object: {path}")

    return data


def _read_count(record: dict[str, Any], field: str, path: Path) -> int:
    value = record.get(field)

    if type(value) is not int or value < 0:
        raise ValueError(
            f"{field} must be a non-negative integer in {path}"
        )

    return value


def _parse_recorded_at(record: dict[str, Any], path: Path) -> datetime:
    value = record.get("recorded_at")

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"recorded_at is missing in {path}")

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(f"Invalid recorded_at in {path}") from error

    if parsed.tzinfo is None:
        raise ValueError(f"recorded_at must include a timezone in {path}")

    return parsed.astimezone(UTC)


def _resolve_metrics_date() -> date:
    context = get_current_context()
    dag_run = context.get("dag_run")
    configured_date: str | None = None

    if dag_run is not None and isinstance(
        getattr(dag_run, "conf", None),
        dict,
    ):
        raw_date = dag_run.conf.get("metrics_date")
        configured_date = str(raw_date).strip() if raw_date else None

    if configured_date:
        try:
            return date.fromisoformat(configured_date)
        except ValueError as error:
            raise ValueError(
                "metrics_date must use YYYY-MM-DD format"
            ) from error

    logical_date = context.get("logical_date")
    local_time = (
        pendulum.instance(logical_date).in_timezone(LOCAL_TIMEZONE)
        if logical_date is not None
        else pendulum.now(LOCAL_TIMEZONE)
    )
    return local_time.subtract(days=1).date()


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _validate_daily_crawl_target(summary: dict[str, Any]) -> dict[str, Any]:
    fetched = int(summary["fetched_count"])
    minimum = int(summary["minimum_fetched"])
    maximum = int(summary["maximum_fetched"])

    if fetched < minimum:
        raise ValueError(
            "Daily crawl volume is below the target range: "
            f"fetched={fetched}, minimum={minimum}"
        )

    target_status = "above_target" if fetched > maximum else "passed"

    return {**summary, "target_status": target_status}


@dag(
    dag_id="job_daily_crawl_metrics",
    description="Aggregate six-source crawl metrics and enforce daily volume",
    schedule="45 0 * * *",
    start_date=pendulum.datetime(2026, 8, 25, tz=LOCAL_TIMEZONE),
    catchup=False,
    max_active_runs=1,
    on_failure_callback=persist_failure_alert,
    tags=["jobs", "metrics", "monitoring"],
)
def job_daily_crawl_metrics() -> None:
    @task(
        task_id="resolve_metrics_configuration",
        retries=0,
        execution_timeout=timedelta(minutes=1),
    )
    def resolve_metrics_configuration() -> dict[str, Any]:
        sources = _parse_sources(
            Variable.get(
                SOURCES_VARIABLE,
                default=",".join(DEFAULT_SOURCES),
            )
        )
        minimum = _positive_int_variable(
            MIN_DAILY_FETCHED_VARIABLE,
            DEFAULT_MIN_DAILY_FETCHED,
        )
        maximum = _positive_int_variable(
            MAX_DAILY_FETCHED_VARIABLE,
            DEFAULT_MAX_DAILY_FETCHED,
        )

        if minimum > maximum:
            raise ValueError(
                "Daily minimum fetched count cannot exceed the maximum"
            )

        return {
            "sources": sources,
            "metrics_date": _resolve_metrics_date().isoformat(),
            "freshness_hours": _positive_int_variable(
                FRESHNESS_HOURS_VARIABLE,
                DEFAULT_FRESHNESS_HOURS,
            ),
            "minimum_fetched": minimum,
            "maximum_fetched": maximum,
            "planned_fetched": PLANNED_DAILY_FETCHED,
        }

    @task(
        task_id="aggregate_daily_crawl_metrics",
        retries=1,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=5),
    )
    def aggregate_daily_crawl_metrics(
        configuration: dict[str, Any],
    ) -> dict[str, Any]:
        metrics_date = str(configuration["metrics_date"])
        totals = {field: 0 for field in COUNT_FIELDS}
        source_summaries: dict[str, dict[str, Any]] = {}

        for source in configuration["sources"]:
            source_totals = {field: 0 for field in COUNT_FIELDS}
            metrics_files = sorted(
                (METRICS_DIRECTORY / source / metrics_date).glob("*.json")
            )

            for metrics_path in metrics_files:
                record = _load_json_record(metrics_path)

                if record.get("source") != source:
                    raise ValueError(
                        f"Metrics source mismatch in {metrics_path}"
                    )

                for field in COUNT_FIELDS:
                    count = _read_count(record, field, metrics_path)
                    source_totals[field] += count
                    totals[field] += count

            source_summaries[source] = {
                "batch_count": len(metrics_files),
                **source_totals,
            }

        return {
            "metrics_date": metrics_date,
            "generated_at": datetime.now(UTC).isoformat(),
            "sources": source_summaries,
            "source_count": len(source_summaries),
            "planned_fetched": configuration["planned_fetched"],
            "minimum_fetched": configuration["minimum_fetched"],
            "maximum_fetched": configuration["maximum_fetched"],
            **totals,
        }

    @task(
        task_id="validate_daily_crawl_target",
        retries=0,
        execution_timeout=timedelta(minutes=1),
    )
    def validate_daily_crawl_target(
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        return _validate_daily_crawl_target(summary)

    @task(
        task_id="persist_daily_crawl_metrics",
        retries=2,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=2),
    )
    def persist_daily_crawl_metrics(
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        output_path = (
            DAILY_METRICS_DIRECTORY
            / f"{summary['metrics_date']}.json"
        )
        _write_json_atomically(output_path, summary)
        return {
            "metrics_date": summary["metrics_date"],
            "daily_metrics_path": str(output_path),
        }

    @task(
        task_id="check_new_job_freshness",
        retries=0,
        execution_timeout=timedelta(minutes=5),
    )
    def check_new_job_freshness(
        configuration: dict[str, Any],
    ) -> dict[str, Any]:
        latest_new_job_at: datetime | None = None
        earliest_recorded_at: datetime | None = None
        valid_record_count = 0

        for source in configuration["sources"]:
            for metrics_path in sorted(
                (METRICS_DIRECTORY / source).glob("*/*.json")
            ):
                try:
                    record = _load_json_record(metrics_path)
                    recorded_at = _parse_recorded_at(record, metrics_path)
                    inserted = _read_count(
                        record,
                        "inserted_count",
                        metrics_path,
                    )
                except ValueError:
                    LOGGER.warning(
                        "Skipping invalid metrics file: %s",
                        metrics_path,
                        exc_info=True,
                    )
                    continue

                valid_record_count += 1

                if (
                    earliest_recorded_at is None
                    or recorded_at < earliest_recorded_at
                ):
                    earliest_recorded_at = recorded_at

                if inserted > 0 and (
                    latest_new_job_at is None
                    or recorded_at > latest_new_job_at
                ):
                    latest_new_job_at = recorded_at

        if valid_record_count == 0 or earliest_recorded_at is None:
            raise ValueError("No valid crawl metrics found")

        reference_time = latest_new_job_at or earliest_recorded_at
        age_hours = max(
            0.0,
            (datetime.now(UTC) - reference_time).total_seconds() / 3600,
        )
        threshold = int(configuration["freshness_hours"])

        if latest_new_job_at is None and age_hours < threshold:
            return {
                "freshness_status": "warming_up",
                "latest_new_job_at": None,
                "age_hours": round(age_hours, 2),
                "threshold_hours": threshold,
            }

        if age_hours >= threshold:
            raise ValueError(
                "No new jobs were inserted for "
                f"{age_hours:.2f} hours; threshold={threshold} hours"
            )

        return {
            "freshness_status": "fresh",
            "latest_new_job_at": (
                latest_new_job_at.isoformat()
                if latest_new_job_at
                else None
            ),
            "age_hours": round(age_hours, 2),
            "threshold_hours": threshold,
        }

    configuration = resolve_metrics_configuration()
    summary = aggregate_daily_crawl_metrics(configuration)
    validated_summary = validate_daily_crawl_target(summary)
    persisted_summary = persist_daily_crawl_metrics(validated_summary)
    freshness_result = check_new_job_freshness(configuration)
    persisted_summary >> freshness_result


job_daily_crawl_metrics()
