-- Source skill labels the taxonomy could not map (stored by the normalizer in
-- source_metadata.unmapped_skills): the to-do list for extending
-- backend/app/data/skill_taxonomy.json.
select
    lower(trim(u.skill))                                            as skill,
    count(distinct j.job_id)                                        as n_jobs,
    count(distinct j.source)                                        as n_sources,
    string_agg(distinct j.source, ', ' order by j.source)           as sources
from {{ ref('stg_jobs') }} as j
cross join lateral jsonb_array_elements_text(
    case
        when jsonb_typeof(j.unmapped_skills) = 'array' then j.unmapped_skills
        else '[]'::jsonb
    end
) as u(skill)
where trim(u.skill) <> ''
group by 1
