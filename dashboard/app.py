import pandas as pd
import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

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


def generate_forecast_accuracy_sql(lead_days: int, days_back: int) -> str:
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


def generate_latest_forecast_sql() -> str:
    """The live forward forecast: the most recent issue's predictions.

    No join to actuals here -- these target hours haven't happened yet, so
    there is nothing to grade. This is the only forward-looking view.

    One row per (target_ts, lead_days) for the latest issue_date.
    """
    sql_text = """
    select 
        target_ts,
        lead_days,
        predicted_mw
    from silver.stg_inference_forecasts
    where issue_date = (select max(issue_date) from silver.stg_inference_forecasts)
    order by target_ts
    """
    return sql_text


def generate_accuracy_over_time_sql(lead_days) -> str:
    """MAE per (issue_date, lead_days) -- the honesty view.

    Grain note: one row per issue_date per lead. Averaging abs_error_mw across
    a day's 24 target hours is what turns ~650 noisy hourly errors into a
    readable series.
    """
    sql_text = f"""
    select
        issue_date, 
        lead_days,
        avg(abs_error_mw) as mae_mw,
        count(*) as num_hours
    from gold.fct_forecast_accuracy
    where actual_mw is not null
    and lead_days = {lead_days}
    group by issue_date, lead_days
    order by issue_date
    """
    return sql_text


def generate_recent_actuals_sql(days_back: int) -> str:
    """The history leg of the forward view: actual demand up to now.

    Straight from silver.int_demand_hourly rather than fct_forecast_accuracy --
    the actual is a property of the hour, not of any forecast, so pulling it
    from the accuracy mart would repeat it once per lead.

    Columns must come back named to MATCH the forecast leg's timestamp column,
    so the two frames stack on one axis.
    """
    sql_text = f"""
    select
        target_hour as target_ts,
        avg_initial_demand_outturn as actual_mw
    from silver.int_demand_hourly
    where target_hour >= current_date - interval '{days_back}' day
    order by target_ts
    """
    return sql_text


def generate_mae_by_lead_sql() -> str:
    """Pooled MAE per lead -- the headline chart: error vs horizon.

    Deliberately a separate query rather than aggregating the
    generate_accuracy_over_time_sql() frame in pandas. This is 
    because a mean of means gives a different answer due to the
    different weights (counts) of each issue_date, so needs to be
    calculated from raw data.
    """
    sql_string = """
    select 
        lead_days,
        avg(abs_error_mw) as mae_mw,
        count(*) as num_hours
    from gold.fct_forecast_accuracy
    where actual_mw is not null
    group by lead_days
    order by lead_days
    """
    return sql_string


st.title("Foresight - GB electricity demand forecast")

max_window = run_query("select date_diff('day', min(target_ts), current_timestamp) as max_days from gold.fct_forecast_accuracy where actual_mw is not null")["max_days"].item()

lead_days = st.sidebar.slider(
"Forecast lead (days)", 
min_value=0,
max_value=7,
value=7,
step=1,
)
days_back = st.sidebar.slider(
    "History window (days)",
    min_value=1,
    max_value=max_window,
    value=max_window,
    step=1,
)

tab_recent, tab_forward, tab_accuracy = st.tabs(
    ["Recent accuracy", "Live forecast", "Accuracy over time"]
)

with tab_recent:
    forecast_accuracy_sql = generate_forecast_accuracy_sql(lead_days, days_back)
    forecast_accuracy_df = run_query(forecast_accuracy_sql)

    st.line_chart(
        forecast_accuracy_df, 
        x="target_ts", 
        y=["actual_mw", "predicted_mw"],
        x_label="Target time",
        y_label="Power demand (MW)",
    )

with tab_forward:
    latest_forecast_sql = generate_latest_forecast_sql()
    latest_forecast_df = run_query(latest_forecast_sql)
    latest_forecast_df.drop("lead_days", axis=1, inplace=True)

    days_back_live = st.slider(
        "History window for live graph (days)",
        min_value=1,
        max_value=4,
        value=4,
        step=1,
    )

    recent_actuals_sql = generate_recent_actuals_sql(days_back_live)
    recent_actuals_df = run_query(recent_actuals_sql)

    actual_w_forecast_df = pd.concat([latest_forecast_df, recent_actuals_df])
    actual_w_forecast_df.sort_values("target_ts", inplace=True)

    st.line_chart(
        actual_w_forecast_df,
        x="target_ts",
        y=["actual_mw", "predicted_mw"],
        x_label="Target time",
        y_label="Power demand (MW)",
    )

with tab_accuracy:
    mae_by_lead_sql = generate_mae_by_lead_sql()
    mae_by_lead_df = run_query(mae_by_lead_sql)

    st.bar_chart(
        mae_by_lead_df,
        x="lead_days",
        y="mae_mw",
        x_label="Lead day",
        y_label="Mean absolute error (MW)",
    )

    accuracy_over_time_sql = generate_accuracy_over_time_sql(lead_days)
    accuracy_over_time_df = run_query(accuracy_over_time_sql)

    st.divider()

    st.bar_chart(
        accuracy_over_time_df,
        x="issue_date",
        y="mae_mw",
        x_label="Issue date",
        y_label="Mean absolute error (MW)",
    )

    st.metric(label="Number of hours measued in this window", value=accuracy_over_time_df["num_hours"].sum())