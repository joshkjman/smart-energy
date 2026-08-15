"""Score the seasonal-naive baseline on the holdout window.

Baseline rule: prediction = demand at the same hour on the most recent
LEGAL same-weekday anchor. That is lag_7d where the publication gate
allows it, and lag_14d at lead 7 where it does not.

Nothing is trained here. This is the bar the model must clear.
"""
import pandas as pd
import datetime as dt
import pathlib
import numpy as np
import duckdb


HOLDOUT_START = dt.date(2025,7,1)   # TODO: the cutoff you chose — one place, reused by the model later
DB_PATH = pathlib.Path(__file__).parent.parent / "dbt" / "foresight.duckdb"


def load_holdout(con) -> pd.DataFrame:
    """Pull target_ts, lead_days, demand_mw, lag_7d, lag_14d from the mart
    for target_ts >= HOLDOUT_START."""
    df = con.execute(
        """
        select target_ts, lead_days, demand_mw, lag_7d, lag_14d
        from gold.fct_demand_features
        where target_ts >= ?
        """,
        [HOLDOUT_START],
    ).df()

    return df


def baseline_prediction(df) -> pd.Series:
    """Return the baseline prediction per row: lag_7d, falling back to
    lag_14d where lag_7d is null."""
    demand_prediction = df['lag_7d'].combine_first(df['lag_14d'])

    return demand_prediction


def rmse(actual, predicted) -> float:
    """Root mean squared error."""
    total = 0
    for a, p in zip(actual, predicted):
        total += (a - p) ** 2
    
    return np.sqrt(total / len(actual))


def score_by_lead(df, score_prediction='baseline_prediction') -> pd.DataFrame:
    """One row per lead_days: n_scored, rmse, and mean demand
    (so the RMSE is interpretable as a % of typical load)."""
    def score_group(g):
        error = rmse(g['demand_mw'], g[score_prediction])
        mean_demand = g['demand_mw'].mean()
        return pd.Series({
            "n": len(g),
            "rmse": error,
            "mean_demand": mean_demand,
            "rmse_pct": (error / mean_demand) * 100
        })

    return df.groupby("lead_days").apply(score_group).reset_index()

    


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = load_holdout(con)
    con.close()

    df['baseline_prediction'] = baseline_prediction(df)
    # some rows are missing any legal anchor from either lag_7d or lag_14d
    df.dropna(subset=['baseline_prediction'], inplace=True)
    grouped_df = score_by_lead(df)

    print(grouped_df)

if __name__ == "__main__":
    main()