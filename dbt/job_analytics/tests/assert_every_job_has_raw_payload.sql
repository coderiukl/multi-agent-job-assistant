{{ config(severity='warn') }}
-- Lineage check: every normalized job should be reproducible from the raw
-- layer (reprocess-raw-jobs). Warn only: jobs imported before the raw layer
-- existed may legitimately lack a payload.
select j.job_id, j.source, j.source_job_id
from {{ ref('stg_jobs') }} as j
where not exists (
    select 1
    from {{ ref('stg_raw_job_records') }} as r
    where r.source = j.source
      and r.source_job_id = j.source_job_id
)
