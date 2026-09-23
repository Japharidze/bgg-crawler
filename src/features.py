"""Step 5 - build the modelling matrix.

Multi-hot mechanics and categories, binned weight and play time, plus the
controls (weight, year) the methodology requires so results are not just
"heavy and recent".
"""

from __future__ import annotations

import argparse
import logging

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
            SELECT id, name, year, min_players, max_players, playing_time, min_age,
                   users_rated, average, bayes_average, std_dev,
                   average_weight, owned, wishing, wanting, trading, rank
            FROM games
            WHERE users_rated >= ?
              AND average IS NOT NULL
              AND average_weight IS NOT NULL
              AND average_weight > 0
            """,
            [min_users_rated],
        ).df()

        links = con.execute(
            "SELECT game_id, link_type, link_value FROM game_links WHERE link_type IN "
            "('boardgamemechanic', 'boardgamecategory')"
        ).df()

    if games.empty:
        raise RuntimeError("no games passed the filter - fetch and parse more data first.")

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
    df["weight_bin"] = pd.cut(
        df.average_weight, bins=WEIGHT_BINS, include_lowest=True
    ).astype(str)
    df["playtime_bin"] = pd.cut(
        df.playing_time, bins=PLAYTIME_BINS, include_lowest=True
    ).astype(str)
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
