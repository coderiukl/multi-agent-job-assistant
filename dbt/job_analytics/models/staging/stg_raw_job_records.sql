-- Raw payload versions; version_number = 1 is the first payload seen.
select
    id                                                          as raw_record_id,
    lower(source)                                               as source,
    source_job_id,
    batch_id,
    payload_hash,
    crawled_at,
    ingested_at,
    row_number() over (
        partition by source, source_job_id
        order by crawled_at, id
    )                                                           as version_number
from {{ source('raw', 'job_records') }}
