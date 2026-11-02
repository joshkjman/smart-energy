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
        avg(baseline_abs_error_mw) as baseline_mae_mw,
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
        avg(baseline_abs_error_mw) as baseline_mae_mw,
        count(*) as num_hours
    from gold.fct_forecast_accuracy
    where actual_mw is not null
    group by lead_days
    order by lead_days
    """
    return sql_string


def generate_headline_sql(lead_days: int) -> str:
    """The KPI row's single source: model vs baseline at ONE lead.

    Returns exactly one row. Everything the metric row shows comes from here,
    so the four numbers are guaranteed consistent with each other -- four
    separate queries could disagree if a nightly run landed between them.
    """
    sql_string = f"""
    select 
        avg(abs_error_mw) as model_mae,
        avg(baseline_abs_error_mw) as baseline_mae,
        count(*) as scored_hours,
        max(issue_date) as latest_issue,
        max(target_ts) as latest_actual,
        count(distinct issue_date) as live_scoring_count,
        ((avg(abs_error_mw) - avg(baseline_abs_error_mw)) / avg(baseline_abs_error_mw)) * 100 as percent_diff
    from gold.fct_forecast_accuracy
    where actual_mw is not null
    and lead_days = {lead_days}
    """
    return sql_string



st.title("Foresight - GB electricity demand forecast")
st.text("Project predicting GB energy demand values 1-7 days ahead.")

max_window = run_query("select date_diff('day', min(target_ts), current_timestamp) as max_days from gold.fct_forecast_accuracy where actual_mw is not null")["max_days"].item()

st.sidebar.subheader("Choosing day filters")
lead_days = st.sidebar.slider(
    "Forecast lead (days):", 
    min_value=0,
    max_value=7,
    value=7,
    step=1,
)
days_back = st.sidebar.slider(
    "History window (days):",
    min_value=1,
    max_value=max_window,
    value=max_window,
    step=1,
)

st.sidebar.divider()
st.sidebar.markdown(
    """
    **About**

    Serverless pipeline forecasting GB electricity demand 1-7 days ahead.

    Every predictor is point-in-time correct: weather features come from
    forecasts *as they were issued*, never from actuals recorded later, so the
    backtest can't see information the live model wouldn't have had.

    Ingestion to S3, transformed with dbt on Athena, LightGBM retrained offline,
    nightly batch inference orchestrated by Step Functions.

    [GitHub](https://github.com/joshkjman/smart-energy)
    """
)

headline = run_query(generate_headline_sql(lead_days))
latest_actual = headline["latest_actual"].item()
latest_issue = headline["latest_issue"].item()
live_scoring_count = headline["live_scoring_count"].item()
st.caption(f"Scored against actuals through {latest_actual} · most recent graded issue {latest_issue} · {live_scoring_count} days of live scoring")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(
        label="Model MAE", 
        value=f"{headline["model_mae"].item():,.0f} MW",
        border=True,
    )

with c2:
    st.metric(
        label="Baseline MAE", 
        value=f"{headline["baseline_mae"].item():,.0f} MW",
        border=True,
    )

with c3:
    st.metric(
        label="Improvement %", 
        value=f"{headline["percent_diff"].item() * -1:,.2f}%",
        border=True,
    )

with c4:
    st.metric(
        label="Scored Hours", 
        value=int(headline["scored_hours"].item()),
        border=True,
    )

tab_recent, tab_forward, tab_accuracy = st.tabs(
    ["Recent accuracy", "Live forecast", "Accuracy over time"]
)

with tab_recent:
    forecast_accuracy_sql = generate_forecast_accuracy_sql(lead_days, days_back)
    forecast_accuracy_df = run_query(forecast_accuracy_sql)
    forecast_accuracy_df.rename(
        columns={
            "actual_mw": "Actual (MW)",
            "predicted_mw": "Predicted (MW)"
        }, inplace=True
    )

    if forecast_accuracy_df.empty:
        st.info("No scored hours in this window — try a longer history.")
    st.line_chart(
        forecast_accuracy_df, 
        x="target_ts", 
        y=["Actual (MW)", "Predicted (MW)"],
        x_label="Target time",
        y_label="Power demand (MW)",
    )

    st.caption(
        "Hourly forecast against what actually happened, at the forecast lead "
        "selected in the sidebar. One lead at a time rather than all eight pooled: "
        "the mart holds one row per (hour, lead), so pooling would stack eight "
        "predictions on every hour and the forecast line would widen into a band. "
        "Drag the lead down and the two lines should move closer together."
    )

with tab_forward:
    latest_forecast_sql = generate_latest_forecast_sql()
    latest_forecast_df = run_query(latest_forecast_sql)
    latest_forecast_df.rename(
        columns={
            "predicted_mw": "Predicted (MW)"
        }, inplace=True
    )
    latest_forecast_df.drop("lead_days", axis=1, inplace=True)

    days_back_live = st.slider(
        "History window for live graph (days):",
        min_value=1,
        max_value=4,
        value=4,
        step=1,
    )

    st.divider()

    recent_actuals_sql = generate_recent_actuals_sql(days_back_live)
    recent_actuals_df = run_query(recent_actuals_sql)
    recent_actuals_df.rename(
        columns={
            "actual_mw": "Actual (MW)",
        }, inplace=True
    )

    actual_w_forecast_df = pd.concat([latest_forecast_df, recent_actuals_df])
    actual_w_forecast_df.sort_values("target_ts", inplace=True)

    if actual_w_forecast_df.empty:
        st.info("No scored hours in this window — try a longer history.")
    st.line_chart(
        actual_w_forecast_df,
        x="target_ts",
        y=["Actual (MW)", "Predicted (MW)"],
        x_label="Target time",
        y_label="Power demand (MW)",
    )

    st.caption(
        "The live forecast: the most recent nightly issue, with recent actuals "
        "alongside it. The two series overlap in time rather than meeting at a "
        "single point -- the chain issues at 22:10 UTC and forecasts eight days "
        "ahead, so the earliest target hours have already happened while the rest "
        "are still unknowable. The stretch beyond the last actual is the part the "
        "model is actually being asked to do."
    )

with tab_accuracy:
    mae_by_lead_sql = generate_mae_by_lead_sql()
    mae_by_lead_df = run_query(mae_by_lead_sql)
    mae_by_lead_df.rename(
        columns={
            "mae_mw": "MAE (MW)",
            "baseline_mae_mw": "Baseline MAE (MW)"
        }, inplace=True
    )

    if mae_by_lead_df.empty:
        st.info("No scored hours in this window — try a longer history.")
    st.bar_chart(
        mae_by_lead_df,
        x="lead_days",
        y=["MAE (MW)", "Baseline MAE (MW)"],
        x_label="Lead day",
        y_label="Mean absolute error (MW)",
        stack=False,
    )

    st.caption(
        "The headline result. Model error against the seasonal-naive baseline -- "
        "the same hour on the most recent same-weekday anchor the publication gate "
        "allows -- at every horizon. The model wins at all eight leads, by a wide "
        "margin at lead 0 where recent demand still carries most of the signal, "
        "and by a steadier margin further out. Bars are side-by-side, not stacked: "
        "each height is its own MAE, not a running total."
    )

    accuracy_over_time_sql = generate_accuracy_over_time_sql(lead_days)
    accuracy_over_time_df = run_query(accuracy_over_time_sql)
    accuracy_over_time_df.rename(
        columns={
            "mae_mw": "MAE (MW)",
            "baseline_mae_mw": "Baseline MAE (MW)"
        }, inplace=True
    )

    st.divider()

    if accuracy_over_time_df.empty:
        st.info("No scored hours in this window — try a longer history.")
    st.bar_chart(
        accuracy_over_time_df,
        x="issue_date",
        y=["MAE (MW)", "Baseline MAE (MW)"],
        x_label="Issue date",
        y_label="Mean absolute error (MW)",
        stack=False,
    )

    st.caption(
        "The honesty view: the same comparison broken out by nightly issue, at the "
        "selected lead. Flat is the good outcome -- it means the headline above is "
        "not an artefact of one lucky week. A spike is a day the pipeline or the "
        "weather forecast went wrong, and those days stay in the average rather "
        "than being dropped."
    )