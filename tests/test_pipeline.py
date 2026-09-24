"""The statistical layers, end to end on synthetic data. Offline, ~1s."""

from __future__ import annotations

import pytest

from src.db import connect, scalar


def test_frame_normalises_unranked_to_null(db, ranks_csv):
    from src.frame import load_ranks

    assert load_ranks(ranks_csv) == 1200
    with connect(read_only=True) as con:
        assert scalar(con, "SELECT count(*) FROM ranks WHERE rank = 0") == 0


def test_sample_spans_the_whole_ranking(db, ranks_csv):
    """The point of stratifying: the draw must not cluster at the top."""
    from src.frame import load_ranks
    from src.sample import build_sample

    load_ranks(ranks_csv)
    build_sample(n_strata=5, per_stratum=40, min_users_rated=30)

    with connect(read_only=True) as con:
        strata = con.execute(
            "SELECT stratum, count(*), min(rank), max(rank) FROM sample "
            "GROUP BY stratum ORDER BY stratum"
        ).fetchall()

    assert len(strata) == 5
    assert all(n == 40 for _, n, _, _ in strata)
    # every stratum covers a distinct, ascending band of the ranking
    highs = [hi for _, _, _, hi in strata]
    assert highs == sorted(highs)
    assert strata[-1][3] > 900, "the bottom stratum must reach the tail of the ranking"


def test_sample_requires_the_frame(db):
    from src.sample import build_sample

    with pytest.raises(RuntimeError, match="ranks"):
        build_sample()


def test_features_builds_multi_hot_tags(db, populated_db):
    from src.features import build_features, tag_columns

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    tags = tag_columns(df)

    assert tags, "expected mechanic/category columns"
    assert all(c.startswith(("mech_", "cat_")) for c in tags)
    assert set(df[tags].to_numpy().ravel()) <= {0, 1}, "multi-hot must be 0/1"
    assert (df.n_mechanics > 0).all()
    assert df.weight_bin.notna().all()


def test_rare_tags_are_dropped(db, populated_db):
    from src.features import build_features, tag_columns

    loose = len(tag_columns(build_features(min_users_rated=200, rare_tag_min_games=1)))
    strict = len(tag_columns(build_features(min_users_rated=200, rare_tag_min_games=10_000)))
    assert strict < loose
    assert strict == 0


def test_stratum_survival_is_reported(db, populated_db, caplog):
    import logging

    from src.features import build_features

    with caplog.at_level(logging.INFO, logger="src.features"):
        build_features(min_users_rated=200, rare_tag_min_games=10)
    assert "stratum survival" in caplog.text


def test_residualising_removes_the_weight_trend(db, populated_db):
    """Ratings are generated from weight; the residual must not keep that."""
    from src.features import build_features
    from src.model import residualise

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    raw = df.average.corr(df.average_weight)
    resid = residualise(df, "average").corr(df.average_weight)

    assert raw > 0.3, "fixture should have a real weight->rating trend"
    assert abs(resid) < abs(raw) / 3, f"residual still tracks weight ({resid:.3f})"


def test_models_report_cross_validated_scores(db, populated_db):
    from src.features import build_features
    from src.model import fit_models

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    results = fit_models(df, "average", n_splits=3)

    assert {"model", "r2_mean", "r2_sd", "mae_mean", "folds"} <= set(results.columns)
    assert (results.folds == 3).all()
    baseline = results.loc[results.model == "mean only", "r2_mean"].iloc[0]
    controls = results.loc[results.model.str.startswith("controls only"), "r2_mean"].iloc[0]
    assert controls > baseline, "controls must beat predicting the mean"


def test_design_regions_ranked_and_filtered(db, populated_db):
    from src.features import build_features
    from src.model import design_regions

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    regions = design_regions(df, ["weight_bin"], min_games=5)

    assert (regions.n_games >= 5).all()
    assert regions.shrunk_resid.is_monotonic_decreasing
    # shrinkage must pull every region's score toward zero
    assert (regions.shrunk_resid.abs() <= regions.mean_resid.abs() + 1e-9).all()


def test_combination_search_enumerates_pairs_and_triples(db, populated_db):
    from src.combinations import search_combinations
    from src.features import build_features

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    out = search_combinations(df, max_order=3, min_games=5)

    assert set(out.order) == {1, 2, 3}, "pairs and triples must both be searched"
    assert (out.n_games >= 5).all()
    for order in (1, 2, 3):
        block = out.loc[out.order == order]
        assert block.tags.str.count(r"\+").eq(order - 1).all(), f"order {order} tag count"
    assert (out.loc[out.order == 1, "lift"] == 0).all(), "a single tag has no parts to beat"


def test_apriori_pruning_is_monotone(db, populated_db):
    """A combination can never occur more often than its own subsets."""
    from src.combinations import search_combinations
    from src.features import build_features

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    out = search_combinations(df, max_order=3, min_games=5)
    by_order = out.groupby("order").n_games.max()
    assert by_order[1] >= by_order[2] >= by_order[3]


def test_combination_search_raises_when_nothing_qualifies(db, populated_db):
    from src.combinations import search_combinations
    from src.features import build_features

    df = build_features(min_users_rated=200, rare_tag_min_games=10)
    with pytest.raises(RuntimeError, match="min_games"):
        search_combinations(df, max_order=2, min_games=10**6)
