"""Step 5 - build the modelling matrix.

Multi-hot mechanics and categories, binned weight and play time, plus the
controls (weight, year) the methodology requires so results are not just
"heavy and recent".
"""

from __future__ import annotations

import argparse
import logging
from typing import cast

import numpy as np
import pandas as pd

from src.config import MIN_USERS_RATED, PLAYTIME_BINS, RARE_TAG_MIN_GAMES, WEIGHT_BINS
from src.db import connect

log = logging.getLogger(__name__)

TAG_TYPES = {"boardgamemechanic": "mech", "boardgamecategory": "cat"}


def _slug(value: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in value]
    return "".join(keep).strip("_").replace("__", "_")


def build_features(
    min_users_rated: int = MIN_USERS_RATED,
    rare_tag_min_games: int = RARE_TAG_MIN_GAMES,
) -> pd.DataFrame:
    with connect() as con:
        games = con.execute(
            """
            SELECT g.id, g.name, g.year, g.min_players, g.max_players, g.playing_time,
                   g.min_age, g.users_rated, g.average, g.bayes_average, g.std_dev,
                   g.average_weight, g.owned, g.wishing, g.wanting, g.trading, g.rank,
                   s.stratum, s.sample_weight
            FROM games g
            LEFT JOIN sample s ON s.id = g.id
            WHERE g.users_rated >= ?
              AND g.average IS NOT NULL
              AND g.average_weight IS NOT NULL
              AND g.average_weight > 0
            """,
            [min_users_rated],
        ).df()

        links = con.execute(
            "SELECT game_id, link_type, link_value FROM game_links WHERE link_type IN "
            "('boardgamemechanic', 'boardgamecategory')"
        ).df()

    if games.empty:
        raise RuntimeError("no games passed the filter - fetch and parse more data first.")

    _report_stratum_survival(min_users_rated)

    links = links[links.game_id.isin(games.id)]
    tag_counts = links.groupby(["link_type", "link_value"]).game_id.nunique()
    kept = tag_counts[tag_counts >= rare_tag_min_games].index
    dropped = len(tag_counts) - len(kept)
    log.info(
        "tags: %d kept, %d dropped (seen in < %d games)", len(kept), dropped, rare_tag_min_games
    )

    links = links.set_index(["link_type", "link_value"]).loc[kept].reset_index()
    links["column"] = [
        f"{TAG_TYPES[t]}_{_slug(v)}" for t, v in zip(links.link_type, links.link_value)
    ]

    multi_hot = (
        pd.crosstab(links.game_id, links.column)
        .clip(upper=1)
        .reindex(games.id.values, fill_value=0)
        .astype("int8")
    )

    df = games.set_index("id").join(multi_hot)
    tag_cols = list(multi_hot.columns)
    df[tag_cols] = df[tag_cols].fillna(0).astype("int8")

    # Controls and binned design parameters.
    # Stored as labels, not Interval dtype, so DuckDB can round-trip the table.
    # cast: pandas types `cut` as always returning the (bins, labels) tuple,
    # but that only happens with retbins=True.
    weight_cut = cast(pd.Series, pd.cut(df.average_weight, bins=WEIGHT_BINS,
                                        include_lowest=True))
    playtime_cut = cast(pd.Series, pd.cut(df.playing_time, bins=PLAYTIME_BINS,
                                          include_lowest=True))
    df["weight_bin"] = weight_cut.astype(str)
    df["playtime_bin"] = playtime_cut.astype(str)
    df["player_span"] = (df.max_players - df.min_players).clip(lower=0)
    df["supports_solo"] = (df.min_players <= 1).astype("int8")
    df["supports_two"] = ((df.min_players <= 2) & (df.max_players >= 2)).astype("int8")
    df["supports_party"] = (df.max_players >= 6).astype("int8")
    df["n_mechanics"] = df[[c for c in tag_cols if c.startswith("mech_")]].sum(axis=1)
    df["n_categories"] = df[[c for c in tag_cols if c.startswith("cat_")]].sum(axis=1)
    df["log_owned"] = np.log1p(df.owned.fillna(0).astype(float))

    df = df.reset_index()

    with connect() as con:
        con.execute("CREATE OR REPLACE TABLE features AS SELECT * FROM df")

    log.info("features: %d games x %d tag columns", len(df), len(tag_cols))
    return df


def _report_stratum_survival(min_users_rated: int) -> pd.DataFrame:
    """How much of each rank stratum survives the ratings floor.

    The stratified sample spans the whole ranking, but low-ranked games mostly
    have few ratings, so a flat floor cuts the bottom strata hardest and quietly
    pulls the modelling set back toward popular games - undoing the sampling
    design. This prints the damage so it is a decision, not an accident.
    """
    with connect() as con:
        survival = con.execute(
            """
            SELECT s.stratum,
                   count(*)                                        AS sampled,
                   count(*) FILTER (WHERE g.users_rated >= ?)      AS survives,
                   round(100.0 * count(*) FILTER (WHERE g.users_rated >= ?)
                         / count(*), 1)                            AS pct,
                   min(s.rank)                                     AS rank_lo,
                   max(s.rank)                                     AS rank_hi
            FROM sample s
            LEFT JOIN games g ON g.id = s.id
            GROUP BY s.stratum ORDER BY s.stratum
            """,
            [min_users_rated, min_users_rated],
        ).df()

    log.info("stratum survival at users_rated >= %d:\n%s",
             min_users_rated, survival.to_string(index=False))
    thin = survival.loc[survival.pct < 25]
    if not thin.empty:
        log.warning(
            "strata %s keep under 25%% of their sample - the ratings floor is "
            "undoing the stratification. Lower --min-users-rated (50-100) or accept "
            "the noise and rely on shrinkage.",
            list(thin.stratum),
        )
    return survival


def tag_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith(("mech_", "cat_"))]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the modelling matrix.")
    ap.add_argument("--min-users-rated", type=int, default=MIN_USERS_RATED)
    ap.add_argument("--rare-tag-min-games", type=int, default=RARE_TAG_MIN_GAMES)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_features(args.min_users_rated, args.rare_tag_min_games)


if __name__ == "__main__":
    main()
