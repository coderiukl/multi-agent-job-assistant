ARG AIRFLOW_VERSION=3.3.1
ARG PYTHON_VERSION=3.12
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
ARG CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /requirements.txt \
    --constraint "${CONSTRAINT_URL}"

# dbt lives in its own virtualenv: its dependency pins must not fight the
# Airflow constraints file. DAGs call /opt/dbt_venv/bin/dbt.
ARG DBT_CORE_VERSION=1.12.7
ARG DBT_POSTGRES_VERSION=1.11.0
USER root
RUN python -m venv /opt/dbt_venv \
 && /opt/dbt_venv/bin/pip install --no-cache-dir \
      "dbt-core==${DBT_CORE_VERSION}" \
      "dbt-postgres==${DBT_POSTGRES_VERSION}" \
 && chown -R airflow:0 /opt/dbt_venv
USER airflow
