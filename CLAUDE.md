# CLAUDE.md — Statistically-driven board game design

## Project goal
Find the combinations of board game design parameters (mechanics, categories, theme,
weight, player count, play time) that are associated with high player ratings and
high ownership, using BoardGameGeek (BGG) data. The output is a shortlist of strong
design "regions" (expected: several combinations on a plateau, not one optimum).
A human then picks one and designs the actual game.

This is a design-space search tool, not a hit predictor. Keep that framing in
analysis and write-ups.

## Data sources (BGG only, official channels)
1. **Ranks CSV dump** — https://boardgamegeek.com/data_dumps/bg_ranks
   ids, names, ranks, average rating for ALL games. Used as the sampling frame.
   Requires an approved application (download while logged in or with token).
2. **XML API2** — https://boardgamegeek.com/xmlapi2/
   - Main endpoint: `thing?id=...&type=boardgame&stats=1`
   - `ratingcomments=1` only for finalist games (expensive, see below).

### Hard rules
- Do NOT scrape BGG HTML or call BGG's private/internal JSON endpoints. Not licensed.
- Use `boardgamegeek.com` — never `www.boardgamegeek.com` (breaks auth).
- Auth header on every request: `Authorization: Bearer <token>`.
  Token is read from env var `BGG_TOKEN`. Never hardcode or commit it.
- Max 20 ids per `thing` call.
- Wait ≥ 5 seconds between requests.
- On 500/503: exponential backoff and retry. On 202: wait and retry.
- Always filter `type=boardgame` (exclude expansions/accessories).
- Cache every raw XML response to disk before parsing. Never re-fetch what is cached.

## Pipeline
1. **Frame** — load ranks CSV into DuckDB.
2. **Sample** — stratified sample across the whole ranking (not just the top).
   Rationale: training only on top games = selection on the outcome.
3. **Fetch** — batch ids by 20, fetch `thing` with `stats=1`, save raw XML to `data/raw/`.
4. **Parse** — XML → tables:
   - `games` (id, name, year, min/max players, playtime, min age, avg rating,
     bayes avg, users rated, avg weight, owned, wishing, wanting, trading, rank)
   - `game_links` (game_id, link_type, link_id, link_value) for mechanics,
     categories, families, designers, publishers
   - `game_polls` (suggested player count, language dependence)
5. **Features** — one-hot / multi-hot mechanics and categories, drop very rare tags
   (threshold configurable), bin weight and playtime.
6. **Model** — see methodology.
7. **Finalists** — for top combinations, optionally pull `ratingcomments=1`
   to study rating distributions (polarization), 100 ratings per page.

## Methodology
- **Primary target:** average rating (NOT geek rating / bayes average — that mixes
  quality with vote count, i.e. marketing reach).
- **Filter:** minimum number of ratings (default 200, configurable) to cut noise.
- **Second target:** `owned` count as a rough sales/reach proxy. Model separately.
- **Controls:** weight and year. BGG users rate heavier and newer games higher;
  make sure results are not just rediscovering "heavy + recent".
- **Models:** start simple and interpretable (regularized regression, decision
  trees), then tree ensembles if useful. Report held-out performance honestly.
- **Look at variance, not only means.** A combination with high mean and wide
  spread means execution dominates and tags matter less.
- **Novelty check:** for each strong combination, count how many games already
  occupy it. High rating + few games = underserved gap.
- Output: ranked list of combinations with mean, spread, n games, ownership.

## Stack
- Python, DuckDB for storage and querying.
- `requests` (or `httpx`) for HTTP, `lxml` for XML parsing.
- Notebooks only for exploration; pipeline code lives in modules.

## Suggested layout
```
data/raw/          # cached XML responses (gitignored)
data/ranks.csv     # BGG ranks dump (gitignored)
db/bgg.duckdb      # (gitignored)
src/fetch.py       # rate-limited, cached API client
src/parse.py       # XML -> tables
src/features.py
src/model.py
notebooks/
```

## Working conventions
- Keep changes small; ask before large refactors or new dependencies.
- The fetcher must be resumable (skip ids already cached).
- Log request counts and failures.
- `.env` and all data files are gitignored.
