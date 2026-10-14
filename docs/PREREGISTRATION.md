# Pre-registration
 
Written by SJ before the first real modelling result. Commit it before running
Gate 1. Any later change gets a dated note below explaining why — never a silent
edit.
 
## Gate 1 — do design tags carry signal beyond controls?
- Target (exact definition, incl. normalisation for time on market):
- Population / filters (min ratings, years, type):
- Controls in the baseline:
- Full model adds:
- Split (time-based: train years / test years):
- Model(s):
- Metric:
- Uncertainty method (bootstrap over test games? fold spread?):
- Pass if:
- Fail if:
- Inconclusive if:
- What I do on each outcome:
## Gate 2 — are ranked regions stable?
- What is ranked, and by what score:
- Resampling scheme (bootstrap / subsample, how many reps):
- Stability measure (top-k overlap, k = ?; Kendall tau):
- Stable if:
- Unstable if:
- What I do on each outcome:
## Sales-proxy validation
- Proxy:
- Ground truth (list of publisher sales milestones, source per row):
- Measure (Spearman?) and what counts as "good enough":
## Changes after registration
<!-- YYYY-MM-DD — what changed — why — was any result seen before the change? -->
 
