"""Step 6b - search over mechanic and category combinations.

`design_regions` in src/model.py aggregates whatever keys you hand it, which
only answers questions you already thought to ask. This module does the
searching: it enumerates tag combinations that actually occur often enough to
measure, and scores every one of them.

The interesting number is not a combination's mean rating - a pair of two
well-rated mechanics will look good without the pairing contributing anything.
It is `lift`: how far the combination beats the best of its own parts. That is
what separates "these two belong together" from "these two are individually
popular".

Enumeration is Apriori-pruned: a triple can only clear `min_games` if all three
of its pairs do, so we build level by level and never materialise the full
C(n, 3).
"""

from __future__ import annotations

import argparse
import logging
from itertools import combinations as iter_combinations

import numpy as np
import pandas as pd

from src.features import tag_columns
from src.model import load_features, residualise

log = logging.getLogger(__name__)


def _stats(resid: np.ndarray, rating: np.ndarray, owned: np.ndarray, k: float) -> dict:
    n = resid.size
    return {
        "n_games": n,
        "mean_rating": float(rating.mean()),
        "sd_rating": float(rating.std(ddof=1)) if n > 1 else float("nan"),
        "mean_resid": float(resid.mean()),
        # Shrink toward 0 by group size so thin combinations do not win on noise.
        "shrunk_resid": float(resid.mean() * n / (n + k)),
        "median_owned": float(np.median(owned)),
    }


def search_combinations(
    df: pd.DataFrame,
    max_order: int = 3,
    min_games: int = 25,
    target: str = "average",
    top_per_order: int | None = None,
) -> pd.DataFrame:
    """Score every tag combination of size 1..max_order occurring >= min_games times.

    Returns one row per combination with n, mean, spread, shrunk residual,
    ownership, and `lift` against the best single tag inside it.
    """
    if max_order < 1:
        raise ValueError("max_order must be >= 1")

    work = df.copy()
    resid_all = residualise(work, target).to_numpy()
    rating_all = work[target].to_numpy()
    owned_all = work["owned"].fillna(0).to_numpy()
    k = float(min_games)

    tags = tag_columns(work)
    matrix = work[tags].to_numpy(dtype=bool)
    log.info("searching %d tags over %d games (min_games=%d)", len(tags), len(work), min_games)

    # --- level 1 -------------------------------------------------------
    counts = matrix.sum(axis=0)
    keep = [i for i in range(len(tags)) if counts[i] >= min_games]
    log.info("order 1: %d/%d tags clear min_games", len(keep), len(tags))

    singles: dict[int, dict] = {}
    rows: list[dict] = []
    for i in keep:
        col = matrix[:, i]
        st = _stats(resid_all[col], rating_all[col], owned_all[col], k)
        singles[i] = st
        rows.append({"order": 1, "tags": tags[i], **st, "lift": 0.0})

    # --- level 2, Apriori over the surviving singles --------------------
    pairs: list[tuple[int, int]] = []
    if max_order >= 2:
        for a, b in iter_combinations(keep, 2):
            col = matrix[:, a] & matrix[:, b]
            n = int(col.sum())
            if n < min_games:
                continue
            pairs.append((a, b))
            st = _stats(resid_all[col], rating_all[col], owned_all[col], k)
            best_part = max(singles[a]["shrunk_resid"], singles[b]["shrunk_resid"])
            rows.append({
                "order": 2,
                "tags": " + ".join(sorted((tags[a], tags[b]))),
                **st,
                "lift": st["shrunk_resid"] - best_part,
            })
        log.info("order 2: %d pairs clear min_games", len(pairs))

    # --- level 3, only triples whose three pairs all survived ------------
    if max_order >= 3:
        pair_set = {frozenset(p) for p in pairs}
        members = sorted({i for p in pairs for i in p})
        n_triples = 0
        for a, b, c in iter_combinations(members, 3):
            if not (
                frozenset((a, b)) in pair_set
                and frozenset((a, c)) in pair_set
                and frozenset((b, c)) in pair_set
            ):
                continue
            col = matrix[:, a] & matrix[:, b] & matrix[:, c]
            n = int(col.sum())
            if n < min_games:
                continue
            n_triples += 1
            st = _stats(resid_all[col], rating_all[col], owned_all[col], k)
            best_part = max(singles[a]["shrunk_resid"], singles[b]["shrunk_resid"],
                            singles[c]["shrunk_resid"])
            rows.append({
                "order": 3,
                "tags": " + ".join(sorted((tags[a], tags[b], tags[c]))),
                **st,
                "lift": st["shrunk_resid"] - best_part,
            })
        log.info("order 3: %d triples clear min_games", n_triples)

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError(
            f"no tag combination reached min_games={min_games}; lower it or fetch more games."
        )
    out["occupancy_pct"] = 100.0 * out.n_games / len(work)
    out = out.sort_values(by=["order", "shrunk_resid"], ascending=[True, False])

    if top_per_order:
        out = out.groupby("order", group_keys=False).head(top_per_order)
    return out.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Search mechanic/category combinations.")
    ap.add_argument("--max-order", type=int, default=3)
    ap.add_argument("--min-games", type=int, default=25)
    ap.add_argument("--target", default="average")
    ap.add_argument("--top", type=int, default=15, help="rows shown per order")
    ap.add_argument("--sort", default="shrunk_resid", choices=["shrunk_resid", "lift"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    df = load_features()
    out = search_combinations(df, args.max_order, args.min_games, args.target)

    pd.set_option("display.width", 200)
    for order in sorted(out.order.unique()):
        block = out.loc[out.order == order].sort_values(by=args.sort, ascending=False)
        print(f"\n=== order {order}, top {args.top} by {args.sort} ===")
        print(block.head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
