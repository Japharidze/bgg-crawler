"""Step 6 - model ratings and reach, then rank design regions.

Two things happen here, and they answer different questions:

1. `fit_models` - how much of the rating (and of ownership) is explained by
   design parameters at all, measured honestly on held-out data. If a
   controls-only baseline is nearly as good as the full model, the tags carry
   little signal and every region ranking below should be read with that in
   mind.
2. `design_regions` - the actual deliverable: a ranked list of parameter
   combinations with mean, spread, n games and ownership, scored on rating
   *residualised on weight and year* so we are not just rediscovering
   "heavy and recent".
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor

from src.db import connect
from src.features import tag_columns

log = logging.getLogger(__name__)

CONTROLS = ["average_weight", "year"]
NUMERIC_EXTRAS = [
    "min_players", "max_players", "playing_time", "min_age",
    "player_span", "supports_solo", "supports_two", "supports_party",
    "n_mechanics", "n_categories",
]
RANDOM_STATE = 20260924


def load_features() -> pd.DataFrame:
    with connect(read_only=True) as con:
        return con.execute("SELECT * FROM features").df()


def design_matrix(df: pd.DataFrame, with_tags: bool = True) -> pd.DataFrame:
    cols = CONTROLS + NUMERIC_EXTRAS + (tag_columns(df) if with_tags else [])
    x = df[cols].copy()
    return x.fillna(x.median(numeric_only=True))


def fit_models(df: pd.DataFrame, target: str = "average") -> pd.DataFrame:
    """Held-out performance for a controls-only baseline and two full models."""
    y = df[target]
    mask = y.notna()
    df, y = df[mask], y[mask]

    x_full = design_matrix(df, with_tags=True)
    x_ctrl = design_matrix(df, with_tags=False)

    idx_train, idx_test = train_test_split(
        df.index, test_size=0.25, random_state=RANDOM_STATE
    )

    candidates = {
        "mean only": (DummyRegressor(strategy="mean"), x_ctrl),
        "controls only (ridge)": (RidgeCV(alphas=np.logspace(-3, 3, 25)), x_ctrl),
        "controls + tags (ridge)": (RidgeCV(alphas=np.logspace(-3, 3, 25)), x_full),
        "controls + tags (tree, depth 5)": (
            DecisionTreeRegressor(max_depth=5, min_samples_leaf=50,
                                  random_state=RANDOM_STATE),
            x_full,
        ),
        "controls + tags (random forest)": (
            RandomForestRegressor(n_estimators=400, min_samples_leaf=5, n_jobs=-1,
                                  random_state=RANDOM_STATE),
            x_full,
        ),
    }

    rows = []
    for label, (estimator, x) in candidates.items():
        estimator.fit(x.loc[idx_train], y.loc[idx_train])
        pred = estimator.predict(x.loc[idx_test])
        rows.append(
            {
                "model": label,
                "target": target,
                "r2_holdout": r2_score(y.loc[idx_test], pred),
                "mae_holdout": mean_absolute_error(y.loc[idx_test], pred),
                "n_train": len(idx_train),
                "n_test": len(idx_test),
            }
        )

    results = pd.DataFrame(rows)
    log.info("held-out performance for `%s`:\n%s", target, results.to_string(index=False))
    return results


def residualise(df: pd.DataFrame, target: str = "average") -> pd.Series:
    """Target with the weight and year effects removed.

    BGG users rate heavier and newer games higher. Ranking regions on the raw
    mean would mostly recover that; ranking on the residual asks the question
    we actually care about: given its weight and vintage, does this region
    over- or under-perform?
    """
    x = design_matrix(df, with_tags=False)[CONTROLS]
    x = x.fillna(x.median())
    y = df[target]
    mask = y.notna()
    model = RidgeCV(alphas=np.logspace(-3, 3, 25)).fit(x[mask], y[mask])
    return pd.Series(y - model.predict(x), index=df.index, name=f"{target}_resid")


def design_regions(
    df: pd.DataFrame,
    keys: list[str],
    min_games: int = 10,
    target: str = "average",
) -> pd.DataFrame:
    """Aggregate the sample into regions defined by `keys` and rank them.

    Deliberately reports spread and n alongside the mean: a high mean with a
    wide spread means execution dominates and the tags matter less, and a high
    mean over few games is an underserved gap rather than a proven winner.
    """
    work = df.copy()
    work[f"{target}_resid"] = residualise(work, target)

    grouped = work.groupby(keys, dropna=False, observed=True)
    regions = grouped.agg(
        n_games=(target, "size"),
        mean_rating=(target, "mean"),
        sd_rating=(target, "std"),
        mean_resid=(f"{target}_resid", "mean"),
        median_owned=("owned", "median"),
        mean_weight=("average_weight", "mean"),
        median_year=("year", "median"),
    )
    regions = regions[regions.n_games >= min_games].copy()

    # Shrink the residual toward 0 by group size so thin regions do not top the
    # list on noise alone (James-Stein style, k tuned to `min_games`).
    k = float(min_games)
    regions["shrunk_resid"] = regions.mean_resid * (regions.n_games / (regions.n_games + k))
    regions["rating_se"] = regions.sd_rating / np.sqrt(regions.n_games)

    return regions.sort_values("shrunk_resid", ascending=False).reset_index()


def novelty(regions: pd.DataFrame, total_games: int) -> pd.DataFrame:
    """Share of the sample already sitting in each region. Small = underserved."""
    out = regions.copy()
    out["occupancy_pct"] = 100.0 * out.n_games / total_games
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit models and rank design regions.")
    ap.add_argument("--target", default="average", choices=["average", "log_owned"])
    ap.add_argument(
        "--keys",
        default="weight_bin,playtime_bin",
        help="comma-separated feature columns that define a region",
    )
    ap.add_argument("--min-games", type=int, default=10)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    df = load_features()
    fit_models(df, args.target)

    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    regions = novelty(design_regions(df, keys, args.min_games, args.target), len(df))
    print(regions.head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
