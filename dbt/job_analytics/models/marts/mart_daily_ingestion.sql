-- Daily raw ingestion per source: payload versions seen, new jobs (first
-- version) and changed postings (later versions). Date in Asia/Ho_Chi_Minh.
select
    (crawled_at at time zone 'Asia/Ho_Chi_Minh')::date             as crawl_date,
    source,
    count(*)                                                        as payload_versions,
    count(*) filter (where version_number = 1)                      as new_jobs,
    count(*) filter (where version_number > 1)                      as changed_jobs,
    count(distinct batch_id)                                        as batches
from {{ ref('stg_raw_job_records') }}
group by 1, 2
