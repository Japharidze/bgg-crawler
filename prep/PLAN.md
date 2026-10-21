# 12-day DS prep program (on BGG data)

6 days a week, 2 weeks. Every day: a **timed drill** (`/drill`, 40 min; 60 min on
mock days) on data you haven't touched, narrated out loud, plus 10 min explaining
one concept with no notes. The rest of the day is the project deliverable.

Code in `prep/` and `analysis/` is written by SJ. Claude teaches and reviews
(`/review`). SQL is out of scope.

| Day | Learning focus | Project deliverable |
|---|---|---|
| 1 | I/O, dtypes, missingness, nested → flat | First real run on ~300 games; data audit; start the full fetch. **Fill `docs/PREREGISTRATION.md` and commit it.** |
| 2 | explode, merge (`validate=`), groupby, multi-hot | Tidy feature table. Join Kaggle snapshots by BGG id. Plot owned/rating vs weight and year. Check sample vs population. |
| 3 | sklearn Pipelines, time split, baselines, bootstrap CI | **Gate 1** → decision memo in `docs/`. Run the `gate-auditor` agent. |
| 4 | Target design, shrinkage | Ownership normalised for time on market (or snapshot growth); proxy validation against publisher sales milestones; distributor feasibility filter. |
| 5 | Regularised linear vs boosting, tuning, nested CV, permutation importance | Model comparison with fold spread; interactions (mechanic × weight). |
| 6 | **Mock 60 min**, full loop | Mistake review; fix recurring habits. |
| 7 | Subgroup discovery, trees | Supply density and gap scoring; external sources joined (only if Gate 1 passed). |
| 8 | Resampling, Kendall tau, top-k overlap | **Gate 2** stability report. `gate-auditor` again. |
| 9 | Effect sizes, multiple comparisons, uncertainty | Region scores with CIs. Optional NLP ablation on descriptions (with leakage audit). |
| 10 | torch: tabular MLP | MLP vs boosting on the same target and split; explain the gap. |
| 11 | Honest writeup, figures | Findings, limitations, README; shortlist for the distributor. |
| 12 | **Final mock 60 min** | Buffer; repo ready to be public. |

If Gate 1 fails: days 4–5 become the reframe-or-writeup branch.

## Daily log
<!-- Day N — date — drill score/time — deliverable status — one-line note -->
<!-- Day 0 — 2026-10-21 — no drill — token setup, no data yet — prereg next -->
