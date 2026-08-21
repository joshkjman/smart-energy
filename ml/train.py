"""Train and evaluate LightGBM on walk-forward folds.

One model per fold, fitted on everything before train_end, predicting the
month from test_start to test_end. Predictions are collected across all
folds and scored per lead, so the result is directly comparable to the
seasonal-naive baseline on the same rows.
"""
import datetime as dt
import lightgbm as lgb
import pandas as pd
import numpy as np

from folds import generate_folds
from score_baseline import rmse, score_by_lead, baseline_prediction
from athena import get_athena_connection



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
WEATHER_FEATURES = ['temperature_2m', 'heating_degrees', 'cooling_degrees']
NON_WEATHER_FEATURES = [f for f in FEATURES if f not in WEATHER_FEATURES]
TARGET = "demand_mw"
CATEGORICAL = [
    'hour',
    'day', 
]


def load_features(con) -> pd.DataFrame:
    """Pull the whole mart -- training history as well as holdout."""
    df = con.cursor().execute(
            """
            select *
            from gold.fct_demand_features 
            """
        ).as_pandas()
    df['hour'] = df['hour'].astype('category')
    df['day'] = df['day'].astype('category')
    return df


PARAMS = {
    'objective':"regression",   # L2 loss -- directly minimises what RMSE measures
    'n_estimators':500,         # number of trees
    'learning_rate':0.05,       # how much each tree contributes; lower = more trees needed
    'num_leaves':31,            # tree complexity. LightGBM grows leaf-wise, not depth-wise
    'min_child_samples':20,     # min rows in a leaf; guards against overfitting noise
    'random_state':42,          # inert here -- see note below
    'n_jobs':-1,
    'verbose':-1,               # otherwise it prints a wall of text per fold
}

# Deliberately untuned. subsample/colsample_bytree are left at their defaults
# of 1.0, so there is no bagging and the fit is fully deterministic -- the seed
# changes nothing. Turning bagging on (subsample=0.8, subsample_freq=1,
# colsample_bytree=0.8) was measured as ~0.05pp better at every lead, but
# taking it would mean picking a hyperparameter by reading the fold scores,
# which is what stops those scores being an honest estimate of generalisation.
# Not worth 0.05pp.

BAGGED = {**PARAMS, 'subsample': 0.8, 'subsample_freq': 1, 'colsample_bytree': 0.8}


def run_fold(train_df, test_df, features: list[str], params) -> pd.DataFrame:
    """Fit on train_df, predict test_df.

    Returns test_df's identifying columns plus a prediction column, so the
    caller can concatenate folds and score once at the end.
    """
    model = lgb.LGBMRegressor(**params)
    model.fit(train_df[features], train_df[TARGET])
    test_df['demand_prediction'] = model.predict(test_df[features])

    return test_df[['lead_days', 'demand_mw', 'target_ts', 'demand_prediction', 'baseline_prediction', 'is_holiday', 'temperature_2m', 'hour', 'day']]


def walk_forward(df, features: list[str], params) -> pd.DataFrame:
    """Run every fold and return all out-of-sample predictions, concatenated."""
    train_start = pd.Timestamp(year=2024, month=7, day=1)

    results = []
    for fold in generate_folds():
        train_end = pd.Timestamp(fold.train_end)
        test_start = pd.Timestamp(fold.test_start)
        test_end = pd.Timestamp(fold.test_end)

        train_df = df[(df['target_ts'] >= train_start) & (df['target_ts'] < train_end)]
        test_df = df[(df['target_ts'] >= test_start) & (df['target_ts'] < test_end)]

        assert not train_df.empty
        assert not test_df.empty
        assert train_df['target_ts'].max() < test_df['target_ts'].min()

        predictions = run_fold(train_df, test_df, features, params)
        results.append(predictions)

    return pd.concat(results, ignore_index=True)


def seed_sweep(df, seeds=(42, 0, 1, 2, 3)) -> pd.DataFrame:
    """Full vs weather-ablated, bagged, once per seed.

    Returns one row per (seed, lead_days) with rmse_pct_full,
    rmse_pct_ablated and their difference -- so the three numbers the
    README quotes all fall out of one groupby.
    """
    df['baseline_prediction'] = baseline_prediction(df)

    runs = []
    for seed in seeds:
        seed_forward_df = walk_forward(df, FEATURES, {**BAGGED, 'random_state': seed})
        seed_forward_df.dropna(subset=['baseline_prediction'], inplace=True)
        seed_ablated_df = walk_forward(df, NON_WEATHER_FEATURES, {**BAGGED, 'random_state': seed})
        seed_ablated_df.dropna(subset=['baseline_prediction'], inplace=True)

        seed_scored_demand_forward_df = score_by_lead(seed_forward_df, 'demand_prediction')
        seed_scored_demand_ablated_df = score_by_lead(seed_ablated_df, 'demand_prediction')

        seed_scored_demand_full_ablated_df = seed_scored_demand_forward_df.merge(seed_scored_demand_ablated_df, on='lead_days', how='left', suffixes=['_full', '_ablated'])
        seed_scored_demand_full_ablated_df['pct_diff'] = seed_scored_demand_full_ablated_df['rmse_pct_ablated'] - seed_scored_demand_full_ablated_df['rmse_pct_full']
        seed_scored_demand_full_ablated_df['seed'] = seed

        runs.append(seed_scored_demand_full_ablated_df)

    all_scored_demand_full_ablated_df = pd.concat(runs, ignore_index=True)
    
    return all_scored_demand_full_ablated_df



def error_by_slice(df, slice_key, score_prediction='demand_prediction') -> pd.DataFrame:
    """One row per group in slice_key: n, mean signed error, rmse, rmse_pct."""
    def score_group(g):
        error = rmse(g['demand_mw'], g[score_prediction])
        mean_demand = g['demand_mw'].mean()
        return pd.Series({
            "n": len(g),
            "rmse": error,
            "mean_demand": mean_demand,
            "rmse_pct": (error / mean_demand) * 100,
            "signed_error_mean": (g['demand_mw'] - g[score_prediction]).mean()
        })

    return df.groupby(slice_key, observed=True).apply(score_group).reset_index()



def main():
    con = get_athena_connection()
    df = load_features(con)
    con.close()

    df['baseline_prediction'] = baseline_prediction(df)

    forward_df = walk_forward(df, FEATURES, PARAMS)
    forward_df.dropna(subset=['baseline_prediction'], inplace=True)
    ablated_df = walk_forward(df, NON_WEATHER_FEATURES, PARAMS)
    ablated_df.dropna(subset=['baseline_prediction'], inplace=True)

    ##### BASELINE SCORE #####
    # scored_baseline_df = score_by_lead(forward_df, 'baseline_prediction')
    # print(scored_baseline_df)

    # scored_demand_df = score_by_lead(forward_df, 'demand_prediction')
    # scored_demand_ablated_df = score_by_lead(ablated_df, 'demand_prediction')

    # ##### PREDICTION SCORE WITH ABLATION COMPARISON #####
    # scored_demand_full_ablated_df = scored_demand_df.merge(scored_demand_ablated_df, on='lead_days', how='left', suffixes=['_full', '_ablated'])
    # scored_demand_full_ablated_df['pct_diff'] = scored_demand_full_ablated_df['rmse_pct_ablated'] - scored_demand_full_ablated_df['rmse_pct_full']
    # print(scored_demand_full_ablated_df)

    # ##### MODEL AGAINST BAGGING #####
    # all_scored_demand_full_ablated_df = seed_sweep(df)
    # print(all_scored_demand_full_ablated_df)

    ##### ERROR ANALYSIS #####
    forward_df['month'] = forward_df['target_ts'].dt.month
    forward_df['temp_band'] = pd.cut(
        forward_df['temperature_2m'],
        bins=[-np.inf, 0, 5, 10, 15, 20, np.inf],
        labels=['<0', '0-5', '5-10', '10-15', '15-20', '20+'],
    )

    for slice in ['is_holiday', 'temp_band', 'month', 'hour', 'day']:
        slice_errors = error_by_slice(forward_df, slice)
        assert slice_errors['n'].sum() == len(forward_df)

        print(slice_errors)
    

if __name__ == '__main__':
    main()