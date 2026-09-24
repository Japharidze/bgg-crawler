"""Step 1 - load the BGG ranks CSV dump into DuckDB as the sampling frame.

The dump (https://boardgamegeek.com/data_dumps/bg_ranks) covers every game, so
it is the only unbiased frame we have. Download it while logged in; it is
gitignored.
"""

from __future__ import annotations

import argparse
import logging

from src.config import RANKS_CSV
from src.db import connect

log = logging.getLogger(__name__)

# Columns we rely on; the dump carries extra per-family rank columns we ignore.
REQUIRED = ["id", "name", "yearpublished", "rank", "bayesaverage", "average", "usersrated"]


def load_ranks(csv_path=RANKS_CSV) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} not found. Download the ranks dump from "
            "https://boardgamegeek.com/data_dumps/bg_ranks (logged in) and save it there."
        )

    with connect() as con:
        con.execute("DROP TABLE IF EXISTS ranks_raw")
        con.execute(
            "CREATE TABLE ranks_raw AS SELECT * FROM read_csv_auto(?, header=true)",
            [str(csv_path)],
        )
        columns = {c.lower() for c in
                   (r[1] for r in con.execute("PRAGMA table_info('ranks_raw')").fetchall())}
        missing = [c for c in REQUIRED if c not in columns]
        if missing:
            raise ValueError(f"ranks CSV is missing expected columns: {missing}")

        # `rank` is 0 for unranked games in the dump; normalise to NULL.
        con.execute(
            """
            CREATE OR REPLACE TABLE ranks AS
            SELECT
                CAST(id AS INTEGER)                              AS id,
                name,
                NULLIF(CAST(yearpublished AS INTEGER), 0)        AS year,
                NULLIF(CAST(rank AS INTEGER), 0)                 AS rank,
                CAST(bayesaverage AS DOUBLE)                     AS bayes_average,
                CAST(average AS DOUBLE)                          AS average,
                CAST(usersrated AS INTEGER)                      AS users_rated,
                COALESCE(CAST(is_expansion AS BOOLEAN), false)   AS is_expansion
            FROM ranks_raw
            """
            if "is_expansion" in columns else
            """
            CREATE OR REPLACE TABLE ranks AS
            SELECT
                CAST(id AS INTEGER)                       AS id,
                name,
                NULLIF(CAST(yearpublished AS INTEGER), 0) AS year,
                NULLIF(CAST(rank AS INTEGER), 0)          AS rank,
                CAST(bayesaverage AS DOUBLE)              AS bayes_average,
                CAST(average AS DOUBLE)                   AS average,
                CAST(usersrated AS INTEGER)               AS users_rated,
                false                                     AS is_expansion
            FROM ranks_raw
            """
        )
        con.execute("DROP TABLE ranks_raw")
        row = con.execute("SELECT count(*), count(rank) FROM ranks").fetchone()
        n, ranked = row if row else (0, 0)

    log.info("loaded %d games into `ranks` (%d ranked)", n, ranked)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Load the BGG ranks dump into DuckDB.")
    ap.add_argument("--csv", default=str(RANKS_CSV))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from pathlib import Path

    load_ranks(Path(args.csv))


if __name__ == "__main__":
    main()
