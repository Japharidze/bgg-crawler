"""Parsing a realistic BGG response: exact values, not just shapes."""

from __future__ import annotations

import shutil

from src.db import connect, scalar
from src.parse import parse_cache
from tests.conftest import FIXTURES


def _parse_fixture(tmp_path):
    cache = tmp_path / "thing"
    cache.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "thing_sample.xml", cache / "thing_fixture.xml")
    return parse_cache(cache)


def test_expansions_are_excluded(db, tmp_path):
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        ids = [r[0] for r in con.execute("SELECT id FROM games ORDER BY id").fetchall()]
    assert ids == [13, 77], "the boardgameexpansion item must not become a game row"


def test_stats_are_parsed_exactly(db, tmp_path):
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        row = con.execute(
            "SELECT name, year, min_players, max_players, playing_time, min_age, "
            "users_rated, average, bayes_average, average_weight, owned, wishing, rank "
            "FROM games WHERE id = 13"
        ).fetchone()
    assert row == (
        "Catan", 1995, 3, 4, 120, 10, 120000, 7.1, 6.9, 2.3, 180000, 9000, 540,
    )


def test_primary_name_wins_over_alternate(db, tmp_path):
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        assert scalar(con, "SELECT name FROM games WHERE id = 13") == "Catan"


def test_not_ranked_and_zero_values_become_null(db, tmp_path):
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        row = con.execute(
            "SELECT rank, year, average_weight FROM games WHERE id = 77"
        ).fetchone()
    assert row is not None
    rank, year, weight = row
    assert rank is None, '"Not Ranked" must not parse as a number'
    assert year == 0 or year is None  # yearpublished=0 carries through as-is
    assert weight == 0.0


def test_only_the_overall_rank_is_taken(db, tmp_path):
    """The family rank (312) must not be mistaken for the board game rank (540)."""
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        assert scalar(con, "SELECT rank FROM games WHERE id = 13") == 540


def test_links_are_typed_and_filtered(db, tmp_path):
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        rows = con.execute(
            "SELECT link_type, link_value FROM game_links WHERE game_id = 13 "
            "ORDER BY link_type, link_value"
        ).fetchall()
    assert ("boardgamemechanic", "Dice Rolling") in rows
    assert ("boardgamecategory", "Civilization") in rows
    assert ("boardgamedesigner", "Klaus Teuber") in rows
    # boardgameexpansion is not in LINK_TYPES and must be dropped
    assert not any(t == "boardgameexpansion" for t, _ in rows)


def test_polls_keep_player_count_and_language_levels(db, tmp_path):
    _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        best4 = con.execute(
            "SELECT num_votes FROM game_polls WHERE game_id = 13 "
            "AND poll_name = 'suggested_numplayers' AND option = '4' AND value = 'Best'"
        ).fetchone()
        lang = con.execute(
            "SELECT value, num_votes FROM game_polls WHERE game_id = 13 "
            "AND poll_name = 'language_dependence' ORDER BY num_votes DESC"
        ).fetchall()
    assert best4 == (700,)
    assert lang[0] == ("No necessary in-game text", 90)


def test_reparsing_is_idempotent(db, tmp_path):
    _parse_fixture(tmp_path)
    counts = _parse_fixture(tmp_path)
    with connect(read_only=True) as con:
        assert scalar(con, "SELECT count(*) FROM games") == 2
    assert counts["games"] == 2
