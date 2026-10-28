# Rounded-domain scoring and Dashboard scenarios

The current rounded scoring export is `result/`. The frozen evidence
baseline remains `result/figure_data/_dependencies/baseline/`; it is never overwritten.

## Rules

- Hazard base weights: P=2, M=1, B=2, T=3. Maximum 16.
- Exposure: food-contact=1, human biomonitoring=1, inventory=3, production=1,
  patent=2, literature=1. Maximum 16.
- Preserve unweighted component scores, including their missing values.
- Sum weighted components separately for H/E, then round each once, half up.
  Thus H=0.5 and E=0.5 become H=1, E=1 and Priority=2.
- Raw weighted sums are `Hazard_score_raw` and `Exposure_score_raw`.
  `*_observed_score` holds the same unrounded weighted sum, not a second score.
- Integer labels: L=0–3, M=4–7, H=8–11, vH=12–16 for default weights.
- Level matrix (rows H, columns E; order vH/H/M/L):
  `[[1,1,2,2],[1,2,3,3],[2,3,4,4],[2,3,4,4]]`.
- Priority score is the sum of the rounded domains. Competition ranking uses
  that integer total, not level or raw fractional scores. Include every boundary
  tie in Top-N. Identifier order is for display only.
- Missing inputs contribute zero in sums, with original missingness/evidence
  retained. An entirely inactive/no-evidence record remains unranked.
- Custom weights currently do not normalize the scale. The interface displays
  each theoretical maximum; fixed label cutpoints remain 4/8/12 unless a valid
  imported configuration specifies others. Weights are 0–100, up to six decimals.

## Reproduce

From `/Users/ruiwang/Projects/APPs/PlastPrior`:

```sh
.venv/bin/python -m plastprior.scenario_export \
  --source result/figure_data/_dependencies/baseline --output result
```

The output directory must not already exist. `--config` accepts the plain JSON
policy or a Dashboard-exported configuration tied to the exact input CSV hash.
This is the supported rescore entry point. The original pipeline and its frozen
policies remain available for reproducing the evidence baseline.

## SQLite contract

- The new `PlastPrior_results.sqlite` retains original `compounds`, all source
  records, embedded stage artifacts and delta snapshots. They remain the baseline
  audit; changing them would invalidate snapshot reconstruction.
- `current_compounds` is the authoritative view for current scores plus original
  detailed evidence. `scenario_results` is the exact current CSV projection.
  Use these for new analyses, not the baseline `compounds` table.
- `scenario_metadata` records the new run, policy, source hashes and code hashes.
  Original `run_metadata` continues to describe the retained baseline archive.
- `PlastPrior_dashboard.sqlite` exposes current scores through `compound_audit`,
  retains baseline scoring separately, and is paired to the new CSV by SHA-256.
- `score_chart_data.csv` contains the same integer scores, labels and ranks for
  downstream plotting. Do not independently round again in R or other plotting code.

Figure maintenance now uses a separate five-level display policy in
`Figure/_shared/five_level_policy.json`, with approval status in `Figure/INDEX.md`.
The new figure-only Level 1 is vH/vH (101 compounds); other former levels move down
one, with those 101 excluded from new Level 2. This does not migrate the formal
CSV/SQLite or Dashboard from their four-level policy. Figures read existing
integer scores; the maintenance workflow neither rescales nor reranks records.
Deferred figures and existing PPTX decks remain the frozen 2026-10-26 baseline
identified by `Figure/figure_sources.json`. Never mix those with approved new
figures without an explicit status review.

## Dashboard

Load the new CSV and its paired Dashboard SQLite. Expand **Scoring weights**,
edit weights, then **Apply weights**. All views use the active results. The sidebar
shows Level and E/H labels; score details show unrounded sums and configuration.

**Save scenario** saves locally against the exact loaded CSV hash. **Restore
saved**, configuration import/export, and result CSV export are supported.
Result CSVs contain current ranks and configuration; they do not overwrite the
original paired CSV/SQLite. Keep the original CSV plus the exported configuration
to restore an exploratory scenario with its evidence. Configuration imports from
a different source CSV are rejected. User scenarios do not publish or replace the
formal database. The upload hash remains tied to the original source during edits.

The Python Decimal and browser BigInt implementations are compared across the
entire 15,125-compound formal export. Both round only after domain aggregation.

The destination is fixed. Replacement is validated and rejects changed data when
existing figure tables have not been refreshed. The retained baseline is read-only.
