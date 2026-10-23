# Drill — day 2 — 2026-10-23

**Time limit: 40 min.** Talk through your reasoning out loud the whole way.

## Data
`data/drill/day02/ranks.csv`: BoardGameGeek's public ranks export, downloaded
this month. One row per item on the site.

## Questions
1. **Load and audit.** Load the file and tell me what in it I shouldn't trust
   as-is. For each problem, say how many rows it affects and what you'd do about
   it.
2. **Reshape.** The client wants to work by *category* (abstract, family, party,
   strategy, ...). Build a long table with one row per game per category, and
   from it a game × category 0/1 table. How many games sit in more than one
   category, and which pair of categories occurs together most often?
3. **Analyse.** "Which category has had the best-rated games over the last ten
   years?" Pick and defend your definitions of *game*, *best-rated* and *last
   ten years*, then answer. Say how confident you are in the ordering.

Ask me about the data or what the client means. I won't answer questions about code.
