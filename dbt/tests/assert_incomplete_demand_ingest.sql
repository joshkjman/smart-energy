select settlement_date, sum(cardinality(data)) as periods
from {{ source('bronze', 'demand')}}
where settlement_date < cast(current_date as varchar)
and settlement_date >= cast(current_date - interval '30' day as varchar)
group by settlement_date
having sum(cardinality(data)) not in (48, 46, 50)