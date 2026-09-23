"""Step 4 - parse cached `thing` XML into DuckDB tables.

Reads only from the disk cache, never the network, so it is cheap to re-run
after a schema change.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lxml import etree

from src.db import connect
from src.fetch import THING_DIR

log = logging.getLogger(__name__)

LINK_TYPES = {
    "boardgamemechanic",
    "boardgamecategory",
    "boardgamefamily",
    "boardgamedesigner",
    "boardgamepublisher",
    "boardgameartist",
}

GAMES_DDL = """
CREATE OR REPLACE TABLE games (
    id             INTEGER PRIMARY KEY,
    name           VARCHAR,
    year           INTEGER,
    min_players    INTEGER,
    max_players    INTEGER,
    playing_time   INTEGER,
    min_playtime   INTEGER,
    max_playtime   INTEGER,
    min_age        INTEGER,
    users_rated    INTEGER,
    average        DOUBLE,
    bayes_average  DOUBLE,
    std_dev        DOUBLE,
    average_weight DOUBLE,
    num_weights    INTEGER,
    owned          INTEGER,
    wishing        INTEGER,
    wanting        INTEGER,
    trading        INTEGER,
    num_comments   INTEGER,
    rank           INTEGER
)
"""

LINKS_DDL = """
CREATE OR REPLACE TABLE game_links (
    game_id    INTEGER,
    link_type  VARCHAR,
    link_id    INTEGER,
    link_value VARCHAR
)
"""

POLLS_DDL = """
CREATE OR REPLACE TABLE game_polls (
    game_id   INTEGER,
    poll_name VARCHAR,
    option    VARCHAR,
    value     VARCHAR,
    num_votes INTEGER
)
"""


def _int(node, attr: str = "value"):
    if node is None:
        return None
    raw = node.get(attr)
    if raw in (None, "", "Not Ranked"):
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _float(node, attr: str = "value"):
    if node is None:
        return None
    raw = node.get(attr)
    if raw in (None, "", "Not Ranked"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _primary_name(item) -> str | None:
    names = item.findall("name")
    for n in names:
        if n.get("type") == "primary":
            return n.get("value")
    return names[0].get("value") if names else None


def parse_item(item):
    """One <item> -> (game row, link rows, poll rows). None if not a board game."""
    if item.get("type") != "boardgame":
        return None, [], []

    gid = int(item.get("id"))
    ratings = item.find("statistics/ratings")

    overall_rank = None
    if ratings is not None:
        for rank in ratings.findall("ranks/rank"):
            if rank.get("name") == "boardgame":
                overall_rank = _int(rank)
                break

    game = (
        gid,
        _primary_name(item),
        _int(item.find("yearpublished")),
        _int(item.find("minplayers")),
        _int(item.find("maxplayers")),
        _int(item.find("playingtime")),
        _int(item.find("minplaytime")),
        _int(item.find("maxplaytime")),
        _int(item.find("minage")),
        _int(ratings.find("usersrated")) if ratings is not None else None,
        _float(ratings.find("average")) if ratings is not None else None,
        _float(ratings.find("bayesaverage")) if ratings is not None else None,
        _float(ratings.find("stddev")) if ratings is not None else None,
        _float(ratings.find("averageweight")) if ratings is not None else None,
        _int(ratings.find("numweights")) if ratings is not None else None,
        _int(ratings.find("owned")) if ratings is not None else None,
        _int(ratings.find("wishing")) if ratings is not None else None,
        _int(ratings.find("wanting")) if ratings is not None else None,
        _int(ratings.find("trading")) if ratings is not None else None,
        _int(ratings.find("numcomments")) if ratings is not None else None,
        overall_rank,
    )

    links = [
        (gid, link.get("type"), int(link.get("id")), link.get("value"))
        for link in item.findall("link")
        if link.get("type") in LINK_TYPES and link.get("id")
    ]

    polls = []
    for poll in item.findall("poll"):
        name = poll.get("name")
        for results in poll.findall("results"):
            option = results.get("numplayers")  # None for non-player-count polls
            for result in results.findall("result"):
                polls.append(
                    (
                        gid,
                        name,
                        option,
                        result.get("value") or result.get("level"),
                        _int(result, "numvotes"),
                    )
                )

    return game, links, polls


def parse_cache(cache_dir: Path = THING_DIR) -> dict[str, int]:
    files = sorted(p for p in cache_dir.glob("*.xml"))
    if not files:
        raise RuntimeError(f"no cached XML in {cache_dir} - run src/fetch.py first.")

    games: dict[int, tuple] = {}
    links: list[tuple] = []
    polls: list[tuple] = []
    skipped = 0

    for path in files:
        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError as exc:
            log.warning("unparseable cache file %s: %s", path.name, exc)
            skipped += 1
            continue
        for item in tree.getroot().findall("item"):
            game, item_links, item_polls = parse_item(item)
            if game is None:
                skipped += 1
                continue
            if game[0] in games:  # same id cached in two batches
                continue
            games[game[0]] = game
            links.extend(item_links)
            polls.extend(item_polls)

    with connect() as con:
        con.execute(GAMES_DDL)
        con.execute(LINKS_DDL)
        con.execute(POLLS_DDL)
        if games:
            con.executemany(
                f"INSERT INTO games VALUES ({','.join('?' * 21)})", list(games.values())
            )
        if links:
            con.executemany("INSERT INTO game_links VALUES (?,?,?,?)", links)
        if polls:
            con.executemany("INSERT INTO game_polls VALUES (?,?,?,?,?)", polls)

    counts = {"files": len(files), "games": len(games), "links": len(links),
              "polls": len(polls), "skipped_items": skipped}
    log.info("parsed %s", counts)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse cached thing XML into DuckDB.")
    ap.add_argument("--cache-dir", default=str(THING_DIR))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parse_cache(Path(args.cache_dir))


if __name__ == "__main__":
    main()
