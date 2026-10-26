# Current manuscript figures

All nine figures use formal run `20261026T024145Z-e97d428a`, policy `priority-hgt10-ege5-v1`. `figure_sources.json` pins the inputs, population and policy hashes.

- Formal inputs: `../output/2026-10-26/PlastPrior_results.csv`, `PlastPrior_results.sqlite` (full analysis), and `PlastPrior_dashboard.sqlite` (Dashboard details).
- Numerical figure tables: `../output/2026-10-26/figure_data/<figure>/`.
- Images: `<figure>/output/`. Each successful build replaces that figure's previous output; no history copy is created.
- Fig. 3b is also exported separately in `Fig3/output/Fig3b.*`.
- Captions: `captions_draft.md`.
- Verification: `../audit_archive/figure_refresh_20261026/`.

High: raw H>10 and E>=5. Moderate: 6<=H<=10 and E>=5, or H>10 and E<5. Otherwise Low for eligible records. Display bins never enter scores, classifications or rankings. Total-score histograms use floor of raw H+E. The heatmap uses floor H/E except 10<H<11 maps to bin 11; this merges 10<H<12 into a categorical column, while bin 10 contains exactly H=10.

Fig. 4 uses four scoring perturbations and two strict hazard thresholds (>9, >11), holding E>=5. Fig. 5 stable High means High at baseline and under all four scoring perturbations, without an additional total threshold.

## Rebuild and verify

Run from the repository root with the project Python environment and installed R packages:

```sh
.venv/bin/python Figure/Fig3/run_plot.py
Rscript Figure/tests/priority_policy.R
.venv/bin/python scripts/audit_figure_refresh.py
.venv/bin/python Figure/verify_figures.py
.venv/bin/python Figure/ExtendedDataFig1/audit_alignment.py
```

The same `run_plot.py` entry point exists for each figure. Quantitative figures use R and export editable SVG/PDF and 600 dpi PNG/TIFF. Combined Fig. 3 is 183 x 215 mm in three rows (a / b+c / d+e); standalone Fig. 3b is 183 x 133 mm. The combined heatmap uses compact display settings independently of its standalone export. Final journal sizing remains an author decision.

Extended Data Fig. 4 is an unedited application screenshot. The verified Dashboard implementation and production bundle are preserved locally in `../audit_archive/dashboard_runtime_20261026/app`. Serve that production build on port 5198, then run `Figure/ExtendedDataFig4/run_plot.py` with Playwright available through `NODE_PATH`. Set `PLASTPRIOR_DASHBOARD_ROOT` to select another explicitly verified Dashboard checkout. Capture verifies the served bundle against that local build, uploads the locked CSV/database pair, and records both bundle and source hashes. This does not deploy the application.

The canonical local project is `/Users/ruiwang/Projects/APPs/PlastPrior`. Run all commands there. The former repair worktree is retained for recovery and is no longer the active workspace. Existing images were copied byte for byte; the relocation receipt in `../audit_archive/workspace_migration_20261026/` records the path-only capture-code change without claiming that the screenshot was regenerated.

`node Figure/update_ppt.mjs [source.pptx] [new-output.pptx]` embeds the current nine figures in a new review deck. Without arguments it uses the most recently modified review deck and a timestamped output name. It never overwrites an existing PPTX. Build files stay in `audit_archive/`.
