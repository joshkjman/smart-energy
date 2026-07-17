select 
    holiday_date,
    division,
    count(*)
from {{ ref('stg_bank_holidays') }}
group by holiday_date, division
having count(*) > 1