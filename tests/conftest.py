"""Shared fixtures: an isolated DuckDB and a synthetic cache, no network."""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

os.environ.setdefault("BGG_TOKEN", "test-token")

FIXTURES = Path(__file__).parent / "fixtures"

MECHANICS = [
    ("Worker Placement", 2082), ("Deck Bag and Pool Building", 2664),
    ("Hand Management", 2040), ("Set Collection", 2004),
    ("Dice Rolling", 2072), ("Tile Placement", 2002), ("Area Majority", 2080),
]
CATEGORIES = [
    ("Economic", 1021), ("Fantasy", 1010), ("Science Fiction", 1016),
    ("Card Game", 1002), ("Abstract Strategy", 1009), ("Party Game", 1030),
]


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Point every module's DuckDB at a throwaway file."""
    from src import db as db_module

    path = tmp_path / "test.duckdb"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    return path


@pytest.fixture
def ranks_csv(tmp_path) -> Path:
    """A ranks dump shaped like the real one, deterministic."""
    rng = random.Random(7)
    lines = ["id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion"]
    for i in range(1, 1201):
        avg = round(rng.uniform(4.5, 8.8), 3)
        lines.append(
            f"{i},Game {i},{rng.randint(1990, 2025)},{i},{avg - 0.4:.3f},{avg},"
            f"{rng.randint(30, 90000)},False"
        )
    path = tmp_path / "ranks.csv"
    path.write_text("\n".join(lines))
    return path


def synthetic_thing_xml(ids: list[int], rng: random.Random) -> str:
    """A `thing?stats=1` response for the given ids.

    Ratings are generated as a real function of weight plus noise, so the
    model layer has something with actual structure to find.
    """
    parts = ['<?xml version="1.0" encoding="utf-8"?><items>']
    for gid in ids:
        weight = round(rng.uniform(1.2, 4.6), 4)
        average = round(4.8 + 0.5 * weight + rng.gauss(0, 0.7), 4)
        links = "".join(
            f'<link type="boardgamemechanic" id="{i}" value="{v}"/>'
            for v, i in rng.sample(MECHANICS, rng.randint(2, 4))
        ) + "".join(
            f'<link type="boardgamecategory" id="{i}" value="{v}"/>'
            for v, i in rng.sample(CATEGORIES, rng.randint(1, 3))
        )
        parts.append(f"""<item type="boardgame" id="{gid}">
<name type="primary" sortindex="1" value="Game {gid}"/>
<yearpublished value="{rng.randint(1990, 2025)}"/>
<minplayers value="{rng.randint(1, 2)}"/><maxplayers value="{rng.randint(3, 8)}"/>
<playingtime value="{rng.choice([20, 45, 60, 90, 120, 180])}"/>
<minplaytime value="30"/><maxplaytime value="120"/><minage value="{rng.randint(8, 14)}"/>
{links}
<statistics page="1"><ratings>
<usersrated value="{rng.randint(200, 60000)}"/><average value="{average}"/>
<bayesaverage value="{average - 0.4:.4f}"/>
<ranks><rank type="subtype" id="1" name="boardgame" friendlyname="Board Game Rank"
 value="{gid}"/></ranks>
<stddev value="1.3"/><owned value="{rng.randint(300, 90000)}"/>
<trading value="50"/><wanting value="80"/><wishing value="900"/>
<numcomments value="400"/><numweights value="200"/><averageweight value="{weight}"/>
</ratings></statistics></item>""")
    parts.append("</items>")
    return "\n".join(parts)


@pytest.fixture
def populated_db(db, ranks_csv, tmp_path, monkeypatch):
    """Frame + sample loaded, and a synthetic XML cache covering the sample."""
    from src import fetch as fetch_module
    from src.frame import load_ranks
    from src.parse import parse_cache
    from src.sample import build_sample

    load_ranks(ranks_csv)
    build_sample(n_strata=5, per_stratum=60, min_users_rated=30)

    cache = tmp_path / "thing"
    cache.mkdir()
    monkeypatch.setattr(fetch_module, "THING_DIR", cache)

    from src.db import connect

    with connect(read_only=True) as con:
        ids = [r[0] for r in con.execute("SELECT id FROM sample ORDER BY id").fetchall()]

    rng = random.Random(11)
    for batch_start in range(0, len(ids), 20):
        batch = ids[batch_start:batch_start + 20]
        (cache / f"thing_{batch_start:05d}.xml").write_text(synthetic_thing_xml(batch, rng))

    parse_cache(cache)
    return cache
