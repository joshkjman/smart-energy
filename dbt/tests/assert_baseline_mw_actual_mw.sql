select actual_mw, baseline_mw
from {{ ref('fct_forecast_accuracy') }}
where actual_mw is not null and baseline_mw is null