"""Train and evaluate LightGBM on walk-forward folds.

One model per fold, fitted on everything before train_end, predicting the
month from test_start to test_end. Predictions are collected across all
folds and scored per lead, so the result is directly comparable to the
seasonal-naive baseline on the same rows.
"""
import datetime as dt
import pathlib

import duckdb
import lightgbm as lgb
import pandas as pd

from folds import generate_folds
from score_baseline import rmse, score_by_lead, baseline_prediction



DB_PATH = pathlib.Path(__file__).parent.parent / "dbt" / "foresight.duckdb"

FEATURES = [
    'hour',
    'day', 
    'lead_days', 
    'is_holiday', 
    'temperature_2m', 
    'heating_degrees', 
    'cooling_degrees', 
    'demand_lag_mw', 
    'lag_7d', 
    'lag_14d'
]
TARGET = "demand_mw"
CATEGORICAL = [
    'hour',
    'day', 
]


def load_features(con) -> pd.DataFrame:
    """Pull the whole mart -- training history as well as holdout."""
    df = con.execute(
            """
            select *
            from fct_demand_features 
            """
        ).df()
    df['hour'] = df['hour'].astype('category')
    df['day'] = df['day'].astype('category')
    return df


def run_fold(train_df, test_df) -> pd.DataFrame:
    """Fit on train_df, predict test_df.

    Returns test_df's identifying columns plus a prediction column, so the
    caller can concatenate folds and score once at the end.
    """
    PARAMS = {
        'objective':"regression",   # L2 loss -- directly minimises what RMSE measures
        'n_estimators':500,         # number of trees
        'learning_rate':0.05,       # how much each tree contributes; lower = more trees needed
        'num_leaves':31,            # tree complexity. LightGBM grows leaf-wise, not depth-wise
        'min_child_samples':20,     # min rows in a leaf; guards against overfitting noise
        'random_state':42,          # without this, two runs give different numbers
        'n_jobs':-1,
        'verbose':-1,               # otherwise it prints a wall of text per fold
    }

    model = lgb.LGBMRegressor(**PARAMS)
    model.fit(train_df[FEATURES], train_df[TARGET])
    test_df['demand_prediction'] = model.predict(test_df[FEATURES])

    return test_df[['lead_days', 'demand_mw', 'target_ts', 'demand_prediction', 'baseline_prediction']]


def walk_forward(df) -> pd.DataFrame:
    """Run every fold and return all out-of-sample predictions, concatenated."""
    timezone = df['target_ts'].dt.tz    # match timezones

    train_start = pd.Timestamp(year=2024, month=7, day=1, tz=timezone)

    results = []
    for fold in generate_folds():
        train_end = pd.Timestamp(fold.train_end, tz=timezone)
        test_start = pd.Timestamp(fold.test_start, tz=timezone)
        test_end = pd.Timestamp(fold.test_end, tz=timezone)

        train_df = df[(df['target_ts'] >= train_start) & (df['target_ts'] < train_end)]
        test_df = df[(df['target_ts'] >= test_start) & (df['target_ts'] < test_end)]

        assert not train_df.empty
        assert not test_df.empty
        assert train_df['target_ts'].max() < test_df['target_ts'].min()

        predictions = run_fold(train_df, test_df)
        results.append(predictions)

    return pd.concat(results, ignore_index=True)


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = load_features(con)
    con.close()
    df['baseline_prediction'] = baseline_prediction(df)
    
    forward_df = walk_forward(df)
    forward_df.dropna(subset=['baseline_prediction'], inplace=True)
    scored_demand_df = score_by_lead(forward_df, 'demand_prediction')
    scored_baseline_df = score_by_lead(forward_df, 'baseline_prediction')

    print(scored_demand_df)
    print(scored_baseline_df)


if __name__ == '__main__':
    main()