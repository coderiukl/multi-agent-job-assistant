from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)

ALERT_DIRECTORY = Path(
    "/opt/airflow/data/jobs/alerts"
)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")


def persist_failure_alert(context: dict[str, Any]) -> None:
    try:
        occurred_at = datetime.now(UTC)

        dag_run = context.get("dag_run")
        task_instance = (
            context.get("task_instance")
            or context.get("ti")
        )
        exception = context.get("exception")

        dag_id = (
            getattr(dag_run, "dag_id", None)
            or "unknown_dag"
        )
        run_id = (
            getattr(dag_run, "run_id", None)
            or context.get("run_id")
            or "unknown_run"
        )
        task_id = (
            getattr(task_instance, "task_id", None)
            or "unknown_task"
        )

        alert = {
            "occurred_at": occurred_at.isoformat(),
            "dag_id": dag_id,
            "run_id": run_id,
            "task_id": task_id,
            "try_number": getattr(
                task_instance,
                "try_number",
                None,
            ),
            "state": str(
                getattr(task_instance, "state", "failed")
            ),
            "exception_type": (
                type(exception).__name__
                if exception
                else None
            ),
            "exception_message": (
                str(exception)
                if exception
                else None
            ),
            "log_url": getattr(
                task_instance,
                "log_url",
                None,
            ),
        }

        date_directory = (
            ALERT_DIRECTORY
            / occurred_at.date().isoformat()
        )
        date_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = "__".join(
            [
                _safe_filename(str(dag_id)),
                _safe_filename(str(run_id)),
                _safe_filename(str(task_id)),
            ]
        )

        alert_path = date_directory / f"{filename}.json"
        temporary_path = alert_path.with_suffix(".tmp")

        temporary_path.write_text(
            json.dumps(
                alert,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(alert_path)

        LOGGER.error(
            "Failure alert persisted to %s",
            alert_path,
        )
    except Exception:
        # Không để lỗi của callback che mất lỗi chính của DAG.
        LOGGER.exception(
            "Could not persist DAG failure alert"
        )