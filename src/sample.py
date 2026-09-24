"""Step 2 - stratified sample across the whole ranking.

Why stratified and not "the top N": training on the best-rated games only is
selection on the outcome. We need the whole range of the response variable, so
we take an equal-sized draw from each rank stratum.

Note on `sample_weight`: with equal-sized deciles and a fixed draw per stratum
the weights come out near-constant, so this design is close to simple random
sampling and nothing downstream needs to reweight. The column is carried into
`features` anyway because that stops being true the moment the strata become
unequal - if you switch to uneven strata, oversample the tail, or the ratings
floor guts the bottom strata, the weights start to matter and are already there.
"""

from __future__ import annotations

import argparse
import logging

from src.db import connect, scalar

log = logging.getLogger(__name__)

DEFAULT_STRATA = 10
DEFAULT_PER_STRATUM = 600
SAMPLE_MIN_USERS_RATED = 30  # below this BGG does not rank a game at all


def build_sample(
    n_strata: int = DEFAULT_STRATA,
    per_stratum: int = DEFAULT_PER_STRATUM,
    min_users_rated: int = SAMPLE_MIN_USERS_RATED,
    seed: float = 0.42,
) -> int:
    with connect() as con:
        if not scalar(
            con, "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'ranks'"
        ):
            raise RuntimeError("`ranks` table missing - run src/frame.py first.")

        con.execute("SELECT setseed(?)", [seed])
        con.execute(
            f"""
            CREATE OR REPLACE TABLE sample AS
            WITH eligible AS (
                SELECT id, name, year, rank, average, users_rated,
                       NTILE({n_strata}) OVER (ORDER BY rank) AS stratum
                FROM ranks
                WHERE NOT is_expansion
                  AND rank IS NOT NULL
                  AND users_rated >= ?
            ),
            drawn AS (
                SELECT *, row_number() OVER (PARTITION BY stratum ORDER BY random()) AS pick
                FROM eligible
            ),
            sizes AS (
                SELECT stratum, count(*) AS stratum_size FROM eligible GROUP BY stratum
            )
            SELECT d.id, d.name, d.year, d.rank, d.average, d.users_rated, d.stratum,
                   s.stratum_size,
                   s.stratum_size / LEAST({per_stratum}, s.stratum_size) AS sample_weight
            FROM drawn d
            JOIN sizes s USING (stratum)
            WHERE d.pick <= {per_stratum}
            """,
            [min_users_rated],
        )
        rows = int(scalar(con, "SELECT count(*) FROM sample") or 0)
        breakdown = con.execute(
            "SELECT stratum, count(*), min(rank), max(rank) "
            "FROM sample GROUP BY stratum ORDER BY stratum"
        ).fetchall()

    log.info("sample: %d games across %d strata", rows, n_strata)
    for stratum, n, lo, hi in breakdown:
        log.info("  stratum %2d: n=%4d ranks %d-%d", stratum, n, lo, hi)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Draw a stratified sample from the ranks frame.")
    ap.add_argument("--strata", type=int, default=DEFAULT_STRATA)
    ap.add_argument("--per-stratum", type=int, default=DEFAULT_PER_STRATUM)
    ap.add_argument("--min-users-rated", type=int, default=SAMPLE_MIN_USERS_RATED)
    ap.add_argument("--seed", type=float, default=0.42)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_sample(args.strata, args.per_stratum, args.min_users_rated, args.seed)


if __name__ == "__main__":
    main()
