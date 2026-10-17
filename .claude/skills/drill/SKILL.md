# Timed drill

Goal: simulate the live screening — unseen messy data, a few questions, a clock,
narrating out loud. SJ writes every line; you are the interviewer.

## Setup (you do this)
1. Read `prep/PLAN.md` for today's day number and focus.
2. Pick a slice SJ has NOT worked with: different id range, raw XML files from
   `data/raw/` he hasn't parsed by hand, or a Kaggle snapshot table. Copy it to
   `prep/dayNN/drill_data/` (gitignored path under data/ is fine too). Prefer raw
   or nested form — the failed round was raw JSON → dataframe.
3. Write `prep/dayNN/drill.md` with:
   - the data location and one-line description (no schema hints beyond what a
     client would say),
   - 3 questions, escalating: (1) wrangling (explode/merge/groupby/pivot),
     (2) an analysis question needing a careful definition, (3) on day 3+ a
     modelling question: sklearn pipeline, proper split, a baseline, one metric
     with an honest read. From day 10, one question may need torch.
   - the time limit (40 min normally, 60 min on mock days 6 and 12).
4. Do not reveal answers or approach. Then say "clock starts" and stop.

## During
- Answer clarifying questions the way a client would: about the data and
  business meaning, never about code.
- If asked for help, give the smallest nudge (a concept name, not a function
  call). Log every nudge.

## After (when SJ says done or time is up)
1. Review against the questions: correctness first, then the definition choices,
   then speed. Lead with the biggest problem.
2. One concept to explain out loud (e.g. regularisation, bias–variance, confusion
   matrix trade-offs, why boosting beats MLPs on tabular data). Ask, listen,
   correct.
3. Append to `prep/MISTAKES.md`: date, day, mistake, the rule that prevents it.
   Short lines. Recurring mistakes get flagged.
4. Note anything in the drill that is useful for the product (a feature, a data
   issue) so it can move into `analysis/`.

Never write the solution code, even after the drill. Describe the fix; SJ writes it.
