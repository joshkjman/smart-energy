import pandas as pd
import streamlit as st
import altair as alt
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ml.athena import get_athena_connection



APPLIANCES = {
    "Dishwasher (eco)": 3,
    "Washing machine": 2,
    "Tumble dryer": 2,
    "EV charge": 6,
    "Custom": None,
}


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


def generate_cheapest_window_sql(window_hours: int) -> str:
    """Lowest-predicted-demand window on each of the next 8 days.

    The practical payoff of the forecast. Demand sets the marginal plant via
    the merit order, so the lowest-demand hours are the cheapest hours -- and
    at leads 2-7 nobody has published a price yet, so a forecast is the only
    way to answer "when should I run this on Thursday".

    Returns one row per target date: the window start, its mean predicted
    demand, and that day's peak for contrast.
    """
    sql_text = f"""
    with f as (
    select 
        target_ts,
        lead_days,
        predicted_mw,
        date(target_ts) as target_date
    from silver.stg_inference_forecasts
    where issue_date = (select max(issue_date) from silver.stg_inference_forecasts)
    ),
    windows as (
    select 
        f.*,
        avg(predicted_mw) over (partition by date(target_ts) order by target_ts rows between current row and {window_hours - 1} following) as window_mean_mw,
        count(*) over (partition by date(target_ts) order by target_ts rows between current row and {window_hours - 1} following) as hours_in_window,
        max(predicted_mw) over (partition by date(target_ts)) as day_peak_mw
    from f
    ),
    ranked as (
    select
        w.*,
        row_number() over (partition by target_date order by window_mean_mw) as rn
    from windows w
    where hours_in_window = {window_hours}
    )
    select 
        lead_days,
        window_mean_mw,
        day_peak_mw,
        format_datetime(target_ts, 'EEE') as day,
        format_datetime(target_ts, 'HH:mm') as window_start,
        format_datetime(date_add('hour', {window_hours}, target_ts), 'HH:mm') as window_end,
        day_peak_mw - window_mean_mw as saving_vs_peak_mw
    from ranked
    where rn = 1
    order by window_mean_mw
    """
    return sql_text


def generate_forecast_grid_sql():
    sql_text = """
    select 
        format_datetime(target_ts, 'EEE dd/MM') as day,
        extract(hour from target_ts) as hour_of_day,
        predicted_mw
    from silver.stg_inference_forecasts
    where issue_date = (select max(issue_date) from silver.stg_inference_forecasts)
    order by target_ts
    """
    return sql_text


st.set_page_config(page_title="Foresight", layout="wide", page_icon=":chart_with_upwards_trend:")
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
st.caption(f"Scored against actuals through {latest_actual} · Most recent graded issue {latest_issue} · {live_scoring_count} days of live scoring")

# st.divider()

c1, c2, c3, c4 = st.columns(4, gap="medium")
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

st.divider()

tab_recent, tab_forward, tab_accuracy, tab_cheapest = st.tabs(
    ["Recent accuracy", "Live forecast", "Accuracy over time", "Best time to use energy"]
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

    st.subheader("Forecast accuracy")
    st.line_chart(
        forecast_accuracy_df, 
        x="target_ts", 
        y=["Actual (MW)", "Predicted (MW)"],
        x_label="Target time",
        y_label="Power demand (MW)",
        color=["#5c6370", "#1f6feb"],
        height=420,
    )

    recent_caption_container = st.container(border=True)
    recent_caption_container.caption(
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

    actual_w_forecast_df = pd.merge(latest_forecast_df, recent_actuals_df, on="target_ts", how="outer")
    actual_w_forecast_df.sort_values("target_ts", inplace=True)

    if actual_w_forecast_df.empty:
        st.info("No scored hours in this window — try a longer history.")

    st.subheader("Forecast with actuals")
    st.line_chart(
        actual_w_forecast_df,
        x="target_ts",
        y=["Actual (MW)", "Predicted (MW)"],
        x_label="Target time",
        y_label="Power demand (MW)",
        color=["#5c6370", "#1f6feb"],
        height=420,
    )

    actual_w_forecast_caption_container = st.container(border=True)
    actual_w_forecast_caption_container.caption(
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

    st.subheader("Error by forecast horizon")
    st.bar_chart(
        mae_by_lead_df,
        x="lead_days",
        y=["MAE (MW)", "Baseline MAE (MW)"],
        x_label="Lead day",
        y_label="Mean absolute error (MW)",
        stack=False,
        color=["#1f6feb", "#9aa3b0"],
        height=360,
    )

    mae_by_lead_caption_container = st.container(border=True)
    mae_by_lead_caption_container.caption(
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

    st.subheader("Error by nightly run")
    st.bar_chart(
        accuracy_over_time_df,
        x="issue_date",
        y=["MAE (MW)", "Baseline MAE (MW)"],
        x_label="Issue date",
        y_label="Mean absolute error (MW)",
        stack=False,
        color=["#1f6feb", "#9aa3b0"],
        height=360,
    )

    accuracy_over_time_caption_container = st.container(border=True)
    accuracy_over_time_caption_container.caption(
        "The honesty view: the same comparison broken out by nightly issue, at the "
        "selected lead. Flat is the good outcome -- it means the headline above is "
        "not an artefact of one lucky week. A spike is a day the pipeline or the "
        "weather forecast went wrong, and those days stay in the average rather "
        "than being dropped."
    )


with tab_cheapest:
    st.subheader("Best time to use energy, next 8 days")

    appliance_choice = st.selectbox("What are you running?", list(APPLIANCES))
    if APPLIANCES[appliance_choice]:
        window_hours = APPLIANCES[appliance_choice]
    else:
        window_hours = st.slider("Usage window length (hours)", 1, 6, 3)

    cheapest_window_sql = generate_cheapest_window_sql(window_hours)
    cheapest_window_df = run_query(cheapest_window_sql)

    if cheapest_window_df.empty:
        st.info("No forecast available — the nightly chain may not have run yet.")
    else:
        best = cheapest_window_df.iloc[0] # ordered by window_mean_mw

        hero = st.container(border=True)
        hero.markdown(f"Best window: **{best["day"]} {best["window_start"]}-{best["window_end"]}**")

        c1, c2, c3 = hero.columns(3)
        with c1:
            st.metric(
                label="Mean demand in window", 
                value=f"{best["window_mean_mw"]:,.0f} MW",
                border=True,
            )

        with c3:
            st.metric(
                label="Demand below day's peak",
                value=f"{best["saving_vs_peak_mw"]:,.0f} MW",
                border=True,
            )

        with c2:
            st.metric(
                label="Days ahead", 
                value=f"{best["lead_days"]} day(s)",
                border=True,
            )

        st.divider()

        forecast_grid_sql = generate_forecast_grid_sql()
        forecast_grid_df = run_query(forecast_grid_sql)
    
        if forecast_grid_df.empty:
            st.info("No forecast grid available — the nightly chain may not have run yet.")
        else:
            chart = (
                alt.Chart(forecast_grid_df)
                .mark_rect()
                .encode(
                    x=alt.X("hour_of_day:O", title="Hour of day"),
                    y=alt.Y("day:O", title=None, sort=None),
                    color=alt.Color("predicted_mw:Q", title="Predicted MW",
                                    scale=alt.Scale(scheme="reds")),
                    tooltip=["day", "hour_of_day", "predicted_mw"],
                )
            )
            st.altair_chart(chart, height=300)


        with st.expander("All eight days"):
            st.dataframe(
                cheapest_window_df, 
                hide_index=True,
                column_order=[
                    "day",
                    "window_start",
                    "window_mean_mw",
                    "day_peak_mw",
                    "saving_vs_peak_mw",
                    "lead_days"
                ],
                column_config={
                    "window_mean_mw": st.column_config.NumberColumn("Window mean demand", format="%,.0f MW"),
                    "day_peak_mw": st.column_config.NumberColumn("Day peak demand", format="%,.0f MW"),
                    "saving_vs_peak_mw": st.column_config.NumberColumn("Power saved", format="%,.0f MW"),
                    "lead_days": "Lead days",
                    "day": "Day of week",
                    "window_start": "Window start time"
                }
            )


    cheapest_window_container = st.container(border=True)
    cheapest_window_container.caption(
        "Lowest predicted demand is a proxy for cheapest, not a price forecast. "
        "Demand drives the marginal plant and therefore wholesale cost; it does "
        "**not** account for wind, which is the larger driver of carbon intensity. "
        "A real tariff recommendation needs the price itself -- see the README's "
        "next steps. Days 2-8 are the useful ones: Octopus publishes Agile prices "
        "only a day ahead, so beyond that a forecast is the only answer available."
    )
