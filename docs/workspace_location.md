# Local workspace and verified results

Use `/Users/ruiwang/Projects/APPs/PlastPrior` as the repository root. Open
`PlastPrior.ipynb` from this directory. `plastprior/` contains the Python package.

## Current files

- `output/2026-10-26/PlastPrior_results.csv`: publication values, ranks and Top-N membership.
- `output/2026-10-26/PlastPrior_results.sqlite`: full analysis and retained evidence.
- `output/2026-10-26/PlastPrior_dashboard.sqlite`: paired Dashboard details.
- `output/2026-10-26/figure_data/`: numerical figure tables.
- `Figure/<figure>/output/`: final images and original build manifests.
- `Figure/Final_Figures_20261026_Revised.pptx`: current nine-figure review deck.

The pre-existing `results` compatibility link now resolves to `output/2026-10-26`.
Use the dated directory when selecting data; no `current` directory is needed.
Historical runs remain under `audit_archive/`, separate from current outputs.

## Migration and recovery

The former repair worktree remains intact. Both working states, generated files
and Git histories were backed up before merging in the sibling
`PlastPrior_backups/20261026_155412_before_merge/` directory. Original input data
and the shared Python environment were not changed. Backups use independent APFS
copy-on-write files, not hard links. This is a local rollback copy, not an off-device backup.

`audit_archive/workspace_migration_20261026/` records relocation verification.
The migration copies scientific data and figures without rerunning scores or
changing rankings. Original build manifests remain intact. A separate code
relocation record identifies the capture-script path change; it is not a new
figure-generation receipt.

The Dashboard code and production bundle needed to reproduce Extended Data Fig. 4
are preserved under `audit_archive/dashboard_runtime_20261026/`. The independent
Dashboard repository in `Projects/APPs` was not merged or overwritten.
The snapshot's existing `node_modules` link uses the installed dependencies in
that repository. `PLASTPRIOR_DASHBOARD_ROOT` can explicitly select another checkout.

## Checks

Run from this repository root:

```sh
.venv/bin/python Figure/verify_figures.py
Rscript Figure/tests/priority_policy.R
.venv/bin/python -m unittest discover -s tests
```

These checks do not regenerate scientific results. Future analysis runs are
separate operations and must follow the score/rank regression checks in the
delivery pipeline.
