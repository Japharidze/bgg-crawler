# bgg-crawler

Design-space search over BoardGameGeek data: which combinations of mechanics,
categories, weight, player count and play time are associated with high player
ratings and high ownership. Output is a shortlist of strong design *regions* for
a human to choose from — not a hit predictor. See `CLAUDE.md` for the full
methodology and the BGG usage rules.

## Setup

```bash
uv venv
uv pip install -e ".[dev]"
cp .env.example .env      # then paste your BGG token into it
```

The token comes from an approved BGG application. It is read from `BGG_TOKEN`
and sent as `Authorization: Bearer ...` on every request.

Download the ranks dump from <https://boardgamegeek.com/data_dumps/bg_ranks>
while logged in and save it as `data/ranks.csv`.

## Pipeline

Each step is a module that can be run on its own; each writes to
`db/bgg.duckdb` and can be re-run.

```bash
python -m src.frame                       # 1. ranks CSV -> `ranks` table
python -m src.sample                      # 2. stratified sample -> `sample`
python -m src.fetch                       # 3. fetch thing?stats=1 -> data/raw/thing/
python -m src.parse                       # 4. XML -> games, game_links, game_polls
python -m src.features                    # 5. modelling matrix -> `features`
python -m src.model --keys weight_bin,playtime_bin   # 6a. models + ranked regions
python -m src.combinations --max-order 3             # 6b. search tag combinations
```

Step 3 is the slow one: 5 seconds per request, 20 ids per request, so ~6000
sampled games take about 25 minutes. It is resumable — interrupt it and re-run,
and it fetches only what is missing.

Step 7 (finalists only, expensive) pulls individual ratings to study
polarization:

```python
from src.fetch import BGGClient, fetch_rating_comments
with BGGClient() as c:
    fetch_rating_comments(game_id=13, client=c)
```

## Combination search

`src.model` only aggregates keys you name, so it answers questions you already
thought to ask. `src.combinations` does the searching: it enumerates every
mechanic/category combination of size 1-3 that occurs in at least `--min-games`
games and scores all of them. Enumeration is Apriori-pruned (a triple can only
clear the floor if all three of its pairs do), so it never materialises the full
C(n, 3).

Sort by `lift`, not by mean rating. Two individually well-rated mechanics will
show a good mean together without the pairing contributing anything; `lift` is
how far a combination beats the best of its own parts, which is what separates
"these belong together" from "these are separately popular".

```bash
python -m src.combinations --min-games 25 --sort lift
```

## What the numbers mean

`src.model` prints two things. First, held-out performance for a
controls-only baseline against the full models — if adding mechanics and
categories barely beats weight-and-year alone, the tags carry little signal and
the region ranking is weak evidence. Second, the ranked regions, scored on
rating **residualised on weight and year** so the list is not just
"heavy and recent" rediscovered.

Read each region on three numbers together:

- `sd_rating` — wide spread means execution dominates and the tags matter less.
- `n_games` / `occupancy_pct` — high rating over few games is an underserved
  gap, not a proven winner.
- `median_owned` — reach, which is a different question from rating and is
  modelled separately (`--target log_owned`).
- `lift` (combination search only) — gain over the best constituent tag.

One thing to watch on the first real run: `src.features` prints per-stratum
survival against the ratings floor. Low-ranked games mostly have few ratings, so
a flat `--min-users-rated 200` cuts the bottom strata hardest and quietly pulls
the modelling set back toward popular games — undoing the stratified sample. If
the bottom strata keep under ~25% of their draw, the run warns you. Lower the
floor to 50-100, or accept the noise and let the shrinkage absorb it.

`shrunk_resid` is the sort key: the mean residual pulled toward zero by group
size, so thin regions do not top the list on noise.

## Tests

```bash
pytest
```

The tests cover the fetch client's rules (batch size, auth header, host,
throttling, 202/503 retries, resumability) with a mock transport — no network
and no token required.

## Layout

```
src/config.py     paths + every tunable (rating floor, rare-tag cutoff, bins)
src/db.py         DuckDB connection
src/frame.py      1. ranks CSV -> DuckDB
src/sample.py     2. stratified sample across the whole ranking
src/fetch.py      3. rate-limited, cached, resumable API client
src/parse.py      4. XML -> tables
src/features.py   5. multi-hot tags, binned weight/playtime
src/model.py      6. models + design-region ranking
tests/
notebooks/        exploration only; pipeline code stays in src/
data/, db/        gitignored
```
