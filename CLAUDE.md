# CLAUDE.md — bgg-crawler

## Two goals, one repo
1. **Product:** find design regions for a board game that *sells*, to be printed and
   sold by a Tbilisi distributor. Output is a shortlist of regions for a human to
   pick from — not a hit predictor.
2. **Learning:** a 12-day prep program for the Toptal Data Science screening
   (timed pandas + sklearn, possibly torch). Every exercise runs on this project's
   data, not toy data. Plan and log: `prep/PLAN.md`.

If the two stop helping each other (drills skipped to chase the project, or the
project bent to fit drills), say so. The fallback is splitting learning into its
own repo.

## Who writes what — read this first
| Area | Who writes code | Claude's role |
|---|---|---|
| `analysis/`, `prep/`, notebooks | **SJ only** | Teach, review, ask questions. Never write or rewrite this code, not even "a quick fix". Point to the line and the concept; SJ fixes it. |
| `src/features.py`, `src/model.py`, `src/combinations.py` | **SJ only** from now on | Same as above. Existing code stays; changes are SJ's. |
| `src/sources/` (new crawlers), `src/fetch.py`, `src/frame.py`, `src/parse.py`, tests for those | Claude may write | Normal coding. Follow `.claude/skills/new-source`. |
| `docs/PREREGISTRATION.md` | **SJ only** | Claude may point out vague or untestable criteria, never fill them in. |

Style: short back-and-forth, push back on bad ideas, no essays. When reviewing,
lead with the most important problem.

## Questions the analysis must answer
- **Gate 1 (around day 3):** does the full model beat the controls-only baseline on
  held-out data, with a CI on the difference? Outcomes: pass / fail / inconclusive.
  Fail → reframe or write up as a negative result. Decided against
  `docs/PREREGISTRATION.md`, which is written *before* the first real result.
- **Gate 2 (around day 8):** are the ranked regions stable under resampling
  (top-k overlap, Kendall tau), or is the ordering noise?
- The naive answer ("popular games are good, make a popular game") is the null to
  beat, not a finding. The question is what is associated with success *beyond*
  year, weight, age on the market and publisher reach.

## Target
Real sales data is not public. Working target: **ownership as a sales proxy**.
- `owned` (and `users_rated`) normalized for time on market. Raw `owned` grows with
  age — never use it raw.
- Prefer ownership *growth* from joined Kaggle BGG snapshots (by BGG id) over
  dividing by age, when snapshots are available.
- Validate the proxy before trusting it: rank correlation of `owned` against
  30–50 publicly announced sales milestones. Note openly that BGG undercounts
  mass-market games.
- Average rating is a secondary target. Bayes average is never a target (mixes
  quality with vote count).
- Kickstarter/Gamefound backers: validation signal only (crowdfunding audience ≠
  retail buyers). Prefer existing public dumps (e.g. Webrobots) over scraping.
- Awards (Spiel des Jahres etc.): treatment/confounder and validation signal, not
  a feature to optimise.

## Methodology rules
- **Time-based split** (train on older release years, test on newer). Random
  KFold is optimistic for "games not yet made". Existing `src/model.py` uses KFold
  — that is SJ's to change.
- **Controls:** year, weight, time on market, and a publisher-size proxy.
- **Leakage watch:** anything measured after release that encodes popularity
  (rank, wishing/trading counts, expansion count, award flags, description text
  mentioning awards or "bestselling") does not go in as a feature for the success
  target.
- Shrink low-vote averages; report effect sizes with uncertainty; correct for
  multiple comparisons when scanning combinations.
- **Feasible region first:** filter to what the distributor can produce and sell
  (price, components, box size, play time, player count, language dependence)
  before ranking. Constraints go in `src/config.py` once known.
- **Supply side:** score regions on performance *and* how many games already
  occupy them. High performance + few games = gap.
- Language: "associated with", never "causes".
- NLP (descriptions) is optional: an ablation on held-out data plus an audit for
  popularity leakage. "Didn't help, here's why" is a valid result. Don't bolt it on.

## Data sources
### BGG (official channels only)
1. **Ranks CSV dump** — https://boardgamegeek.com/data_dumps/bg_ranks — sampling frame.
2. **XML API2** — https://boardgamegeek.com/xmlapi2/ — `thing?id=...&type=boardgame&stats=1`;
   `ratingcomments=1` only for finalists.

Hard rules:
- Do NOT scrape BGG HTML or call BGG's private/internal JSON endpoints.
- Use `boardgamegeek.com`, never `www.boardgamegeek.com` (breaks auth).
- `Authorization: Bearer <token>` on every request, from env `BGG_TOKEN`. Never
  hardcode, log or commit it.
- Max 20 ids per `thing` call; ≥ 5 s between requests; backoff on 500/503; wait
  and retry on 202.
- Always `type=boardgame`. Cache every raw response before parsing; never re-fetch
  what is cached.

### Other sources
Kaggle BGG snapshots, Kickstarter/Gamefound, publisher sales announcements,
SPIEL/awards lists, the distributor's own sales. Each new source: check ToS and
look for an existing dump before writing a crawler. See `.claude/skills/new-source`.

## Pipeline
`frame → sample → fetch → parse → features → model → combinations`
(details and commands in README.md). Each step writes to `db/bgg.duckdb` and is
re-runnable. Fetch is resumable.

## Layout
```
src/            pipeline (see README); src/sources/ for non-BGG crawlers
analysis/       SJ's analysis code (gates, targets, regions)
prep/           12-day program: PLAN.md, dayNN/ drills and mistake log
docs/           PREREGISTRATION.md, findings
notebooks/      exploration only
data/, db/      gitignored
.claude/        skills (drill, review, new-source) and agents (gate-auditor)
```

## Conventions
- Small changes; ask before refactors or new dependencies.
- `.env` and all data files are gitignored.
- Log request counts and failures.
- Tests run without network or token.
