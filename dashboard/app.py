import pandas as pd
import streamlit as st

from ml.athena import get_athena_connection


st.set_page_config(page_title="Foresight", layout="wide")


@st.cache_data(ttl=900)
def run_query(sql: str) -> pd.DataFrame:
    """Run `sql` against the gold schema and return the result as a frame.

    Cached for 15 min: without this, every slider nudge re-bills Athena and
    re-pays the 1-3 s plan time. st.cache_data keys on the arguments, so each
    distinct `sql` string gets its own entry.
    """
    conn = get_athena_connection()
    cur = conn.cursor()
    df = cur.execute(sql).as_pandas()
    conn.close()
    
    return df


def generate_sql(lead_days: int, days_back: int) -> str:
    """Scored hours at ONE lead: target_ts, predicted_mw, actual_mw.

    Why the lead is fixed rather than pooled: fct_forecast_accuracy has one row
    per (target_ts, lead_days), so pooling would put up to 8 predictions on each
    hour and the forecast line would fan into a band.

    Returns rows ordered by target_ts, oldest first, with unscored hours dropped.
    """
    sql_string = f"""
        select 
            target_ts,
            actual_mw,
            predicted_mw
        from gold.fct_forecast_accuracy
        where lead_days = {lead_days}
        and target_ts >= current_date - interval '{days_back}' day
        and actual_mw is not null
        order by target_ts
    """
    return sql_string


st.title("Foresight - GB electricity demand forecast")

min_history_wind = run_query("select min(target_ts) from gold.fct_forecast_accuracy where actual_mw is not null")

lead_days = st.sidebar.slider(
    "Forecast lead (days)", 
    min_value=0,
    max_value=7,
    value=7,
    step=1,
)
days_back = st.sidebar.slider(
    "History window (days)",
    min_value=0,
    max_value=min_history_wind,
    value=min_history_wind,
    step=1,
)

sql_string = generate_sql(lead_days, days_back)
df = run_query(sql_string)

st.line_chart(
    df, 
    x="target_ts", 
    y=["actual_mw", "predicted_mw"],
    x_label="Target time",
    y_label="Power demand (MW)",
)


def generate_latest_forecast_sql() -> str:
    """The live forward forecast: the most recent issue's predictions.

    No join to actuals here -- these target hours haven't happened yet, so
    there is nothing to grade. This is the only forward-looking view.

    One row per (target_ts, lead_days) for the latest issue_date.
    """
    # TODO:
    #   - from silver.stg_inference_forecasts
    #   - select target_ts, predicted_mw, lead_days
    #   - restrict to the latest issue: issue_date = (select max(issue_date) from ...)
    #     a scalar subquery keeps it correct without a second round trip
    #   - order by target_ts


def generate_accuracy_over_time_sql() -> str:
    """MAE per (issue_date, lead_days) -- the honesty view.

    Grain note: one row per issue_date per lead. Averaging abs_error_mw across
    a day's 24 target hours is what turns ~650 noisy hourly errors into a
    readable series.
    """
    # TODO:
    #   - from gold.fct_forecast_accuracy
    #   - avg(abs_error_mw) as mae_mw, and count(*) so the page can show how
    #     many hours each point rests on
    #   - where actual_mw is not null
    #   - group by issue_date, lead_days
    #   - order by issue_date
