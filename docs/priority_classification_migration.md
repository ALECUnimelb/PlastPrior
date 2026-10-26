# Current priority classification and reproducible migration

The current analysis policy is `priority-hgt10-ege5-v1`. It replaces only the
classification of eligible compounds, not their scores or ranks:

- High: H > 10 and E >= 5.
- Moderate: 6 <= H <= 10 and E >= 5, or H > 10 and E < 5.
- Low: all other eligible records.
- No data: no available component evidence; no total score or rank.

H = 2P + 2B + M + 3T, E is the sum of the six exposure contributions, and S = H + E.
All calculations and ranks use unrounded values. Missing components contribute
zero only to sums; their raw missingness and evidence admission remain unchanged.
The frozen historical reproduction uses `historical_tier()` with the original
S/H/E dual gates, independently of the current analysis classifier.

`PlastPrior.ipynb` and `main.py` call the same scientific modules. Restart the
Notebook kernel before executing changed code. The source Notebook remains
output-free. For the approved migration, set `PRIORITY_MIGRATION_BASELINE` to the
previous verified publication CSV and choose an unused `RESULTS_DIR`. The CLI
supports the equivalent `--priority-migration-baseline` and `--output-dir` flags.

The explicit migration validates every compound by full InChIKey before daily
publication. Only `Priority_tier` and `priority_scoring_policy` may change; all
other publication fields, including scores, ranks, tie sizes, Top-N selections,
source annotations and missingness, must match exactly. Both old and new tiers
are independently checked against literal inequalities. The migration refuses
an existing output directory and writes `priority_migration.json` beside the
new archive. Ordinary publication regression remains strict and unchanged.

Historical archives and previously generated figures are preserved. The existing
figure source lock, R sensitivity code, ADI report scripts and Dashboard classifier
still describe the previous analysis until the separate figure/application
migration is performed. In particular, do not regenerate old-policy figures
against the new policy by bypassing their source-lock checks. Display binning
is never a scoring operation, and the approved heatmap is a comparison reference,
not the input to the scientific calculation.
