with expected as (
    select sequence_date
    from unnest(sequence(
        current_date - interval '30' day,
        current_date - interval '1' day,
        interval '1' day
    )) as t(sequence_date)
),
present as (
    select
        distinct settlement_date
    from {{ source('bronze', 'demand') }}
    where settlement_date >= cast(current_date - interval '30' day as varchar)
)
select sequence_date
from expected e
left join present p 
on date_format(e.sequence_date, '%Y-%m-%d') = p.settlement_date
where p.settlement_date is null