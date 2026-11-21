"""dbt analytics layer over the jobs database.

Runs after the daily crawl-metrics DAG (00:45): checks source freshness of
public.jobs / raw.job_records, then ``dbt build`` (staging views, marts, data
tests in dependency order). The project is mounted read-only, so dbt writes
its target/ and logs/ to /tmp.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task
from common.callbacks import persist_failure_alert

LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
DBT_EXECUTABLE = "/opt/dbt_venv/bin/dbt"
DBT_PROJECT_DIR = "/opt/project/dbt/job_analytics"
DBT_ARGS = (
    f"--project-dir {DBT_PROJECT_DIR} "
    f"--profiles-dir {DBT_PROJECT_DIR} "
    "--target-path /tmp/dbt/target "
    "--log-path /tmp/dbt/logs "
    "--no-use-colors"
)


def dbt_command(subcommand: str) -> str:
    return f"{DBT_EXECUTABLE} {subcommand} {DBT_ARGS}"


@dag(
    dag_id="job_analytics_dbt",
    description="dbt staging/marts and data tests over public.jobs and raw.job_records",
    schedule="15 1 * * *",
    start_date=pendulum.datetime(2026, 11, 19, tz=LOCAL_TIMEZONE),
    catchup=False,
    max_active_runs=1,
    on_failure_callback=persist_failure_alert,
    tags=["jobs", "analytics", "dbt"],
)
def job_analytics_dbt() -> None:
    @task.bash(
        task_id="dbt_source_freshness",
        retries=1,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(minutes=5),
    )
    def dbt_source_freshness() -> str:
        return dbt_command("source freshness")

    @task.bash(
        task_id="dbt_build",
        retries=1,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(minutes=20),
    )
    def dbt_build() -> str:
        return dbt_command("build")

    dbt_source_freshness() >> dbt_build()


job_analytics_dbt()
