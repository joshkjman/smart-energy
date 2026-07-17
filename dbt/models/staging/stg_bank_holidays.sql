with raw as (
    select
        unnest("england-and-wales".events) as e,
        'eng&wales' as division
    from {{ source('bronze', 'bank_holidays') }}
    union all
    select
        unnest("scotland".events) as e,
        'scotland' as division
    from {{ source('bronze', 'bank_holidays') }}
)
select
    e.date::date as holiday_date,
    e.title,
    division
from raw