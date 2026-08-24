from __future__ import annotations

import json
import logging
import re
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

SOURCE_VARIABLE = "job_metrics_source"
FRESHNESS_HOURS_VARIABLE = "job_no_new_data_hours"

DEFAULT_SOURCE = "himalayas"
DEFAULT_FRESHNESS_HOURS = 24

COUNT_FIELDS = (
    "fetched_count",
    "normalized_count",
    "failed_count",
    "inserted_count",
    "updated_count",
    "unchanged_count",
)

SAFE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")

def _validate_source(source: str) -> str:
    normalized_source = source.strip()

    if not normalized_source:
        raise ValueError("Metrics source must not be empty")

    if not SAFE_NAME_PATTERN.fullmatch(normalized_source):
        raise ValueError(
            "Metrics source contains unsupported characters: "
            f"{normalized_source!r}"
        )

    return normalized_source

def _load_json_record(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not read metrics file: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Metrics file must contain a JSON object: {path}"
        )

    return data

def _read_count(record: dict[str, Any], field: str, path: Path) -> int:
    value = record.get(field)

    if type(value) is not int:
        raise ValueError(
            f"{field} must be an integer in {path}, got {value!r}"
        )

    if value < 0:
        raise ValueError(
            f"{field} cannot be negative in {path}"
        )

    return value

def _parse_recorded_at(record: dict[str, Any], path: Path) -> datetime:
    value = record.get("recorded_at")

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"recorded_at is missing in {path}"
        )

    normalized_value = value.strip().replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid recorded_at in {path}: {value!r}"
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            f"recorded_at must contain timezone information in {path}"
        )

    return parsed.astimezone(UTC)

def _resolve_metrics_date() -> date:
    context = get_current_context()
    dag_run = context.get("dag_run")

    configured_date: str | None = None

    if dag_run is not None:
        conf = getattr(dag_run, "conf", None)

        if isinstance(conf, dict):
            raw_date = conf.get("metrics_date")

            if raw_date is not None:
                configured_date = str(raw_date).strip()

    if configured_date:
        try:
            return date.fromisoformat(configured_date)
        except ValueError as exc:
            raise ValueError(
                "metrics_date must use YYYY-MM-DD format"
            ) from exc

    logical_date = context.get("logical_date")

    if logical_date is None:
        local_now = pendulum.now(LOCAL_TIMEZONE)
    else:
        local_now = pendulum.instance(logical_date).in_timezone(LOCAL_TIMEZONE)

    return local_now.subtract(days=1).date()

def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(".tmp")

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)

@dag(
    dag_id="job_daily_crawl_metrics",
    description=(
        "Aggregate daily crawl metrics and monitor job data freshness"
    ),
    schedule="15 0 * * *",
    start_date=pendulum.datetime(
        2026,
        8,
        24,
        tz=LOCAL_TIMEZONE,
    ),
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
        raw_source = Variable.get(
            SOURCE_VARIABLE,
            default=DEFAULT_SOURCE,
        )
        source = _validate_source(str(raw_source))

        raw_freshness_hours = Variable.get(
            FRESHNESS_HOURS_VARIABLE,
            default=str(DEFAULT_FRESHNESS_HOURS),
        )

        try:
            freshness_hours = int(raw_freshness_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{FRESHNESS_HOURS_VARIABLE} must be an integer"
            ) from exc

        if freshness_hours < 1:
            raise ValueError(
                f"{FRESHNESS_HOURS_VARIABLE} must be greater than zero"
            )

        metrics_date = _resolve_metrics_date()

        configuration = {
            "source": source,
            "metrics_date": metrics_date.isoformat(),
            "freshness_hours": freshness_hours,
        }

        LOGGER.info(
            "Daily metrics configuration resolved: %s",
            configuration,
        )

        return configuration

    @task(
        task_id="aggregate_daily_crawl_metrics",
        retries=1,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=5),
    )
    def aggregate_daily_crawl_metrics(configuration: dict[str, Any]) -> dict[str, Any]:
        source = str(configuration["source"])
        metrics_date = str(configuration["metrics_date"])

        metrics_directory = (
            METRICS_DIRECTORY
            / source
            / metrics_date
        )

        metrics_files = sorted(metrics_directory.glob("*.json"))

        totals = {
            field: 0
            for field in COUNT_FIELDS
        }

        batch_ids: list[str] = []

        for metrics_path in metrics_files:
            record = _load_json_record(metrics_path)

            record_source = record.get("source")

            if record_source != source:
                raise ValueError(
                    "Metrics source mismatch in "
                    f"{metrics_path}: {record_source!r}"
                )

            for field in COUNT_FIELDS:
                totals[field] += _read_count(
                    record,
                    field,
                    metrics_path,
                )

            batch_id = record.get("batch_id")

            if isinstance(batch_id, str) and batch_id:
                batch_ids.append(batch_id)

        summary = {
            "source": source,
            "metrics_date": metrics_date,
            "generated_at": datetime.now(UTC).isoformat(),
            "batch_count": len(metrics_files),
            **totals,
            "batch_ids": batch_ids,
        }

        LOGGER.info(
            "Daily crawl metrics aggregated: %s",
            summary,
        )

        return summary

    @task(
        task_id="persist_daily_crawl_metrics",
        retries=2,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=2),
    )
    def persist_daily_crawl_metrics(summary: dict[str, Any]) -> dict[str, Any]:
        source = _validate_source(str(summary["source"]))
        metrics_date = str(summary["metrics_date"])

        output_path = (
            DAILY_METRICS_DIRECTORY
            / source
            / f"{metrics_date}.json"
        )

        _write_json_atomically(
            output_path,
            summary,
        )

        LOGGER.info(
            "Daily crawl metrics persisted to %s",
            output_path,
        )

        return {
            "source": source,
            "metrics_date": metrics_date,
            "daily_metrics_path": str(output_path),
        }

    @task(
        task_id="check_new_job_freshness",
        retries=0,
        execution_timeout=timedelta(minutes=5),
    )
    def check_new_job_freshness(configuration: dict[str, Any]) -> dict[str, Any]:
        source = _validate_source(
            str(configuration["source"])
        )
        freshness_hours = int(
            configuration["freshness_hours"]
        )

        source_directory = METRICS_DIRECTORY / source
        metrics_files = sorted(
            source_directory.glob("*/*.json")
        )

        now = datetime.now(UTC)

        earliest_recorded_at: datetime | None = None
        latest_new_job_at: datetime | None = None
        valid_record_count = 0

        for metrics_path in metrics_files:
            try:
                record = _load_json_record(metrics_path)

                if record.get("source") != source:
                    continue

                recorded_at = _parse_recorded_at(
                    record,
                    metrics_path,
                )
                inserted_count = _read_count(
                    record,
                    "inserted_count",
                    metrics_path,
                )
            except ValueError:
                LOGGER.warning(
                    "Skipping invalid historical metrics file: %s",
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

            if inserted_count > 0 and (
                latest_new_job_at is None
                or recorded_at > latest_new_job_at
            ):
                latest_new_job_at = recorded_at

        if valid_record_count == 0:
            raise ValueError(
                f"No valid crawl metrics found for source {source!r}"
            )

        reference_time = (
            latest_new_job_at
            or earliest_recorded_at
        )

        if reference_time is None:
            raise ValueError(
                f"Could not determine freshness for source {source!r}"
            )

        age = now - reference_time
        age_hours = max(
            0.0,
            age.total_seconds() / 3600,
        )

        if (
            latest_new_job_at is None
            and age_hours < freshness_hours
        ):
            result = {
                "source": source,
                "freshness_status": "warming_up",
                "latest_new_job_at": None,
                "age_hours": round(age_hours, 2),
                "threshold_hours": freshness_hours,
            }

            LOGGER.warning(
                "New-job freshness monitoring is warming up: %s",
                result,
            )

            return result

        if age_hours >= freshness_hours:
            raise ValueError(
                "No new jobs were inserted for "
                f"{age_hours:.2f} hours; "
                f"threshold={freshness_hours} hours; "
                f"source={source}"
            )

        result = {
            "source": source,
            "freshness_status": "fresh",
            "latest_new_job_at": (
                latest_new_job_at.isoformat()
                if latest_new_job_at
                else None
            ),
            "age_hours": round(age_hours, 2),
            "threshold_hours": freshness_hours,
        }

        LOGGER.info(
            "New-job freshness validation passed: %s",
            result,
        )

        return result

    configuration = resolve_metrics_configuration()

    summary = aggregate_daily_crawl_metrics(configuration)

    persisted_summary = persist_daily_crawl_metrics(summary)

    freshness_result = check_new_job_freshness(configuration)

    persisted_summary >> freshness_result


job_daily_crawl_metrics()
