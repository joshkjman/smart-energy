with raw as (
    select
        r,
        'eng&wales' as division
    from {{ source('bronze', 'bank_holidays') }}
    cross join unnest(england_and_wales.events) as t(r)
    union all
    select
        r,
        'scotland' as division
    from {{ source('bronze', 'bank_holidays') }}
    cross join unnest(scotland.events) as t(r)
)
select
    cast(r."date" as date) as holiday_date,
    r.title,
    division
from raw