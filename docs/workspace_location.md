# Local workspace and current results

Use `/Users/ruiwang/Projects/APPs/PlastPrior` as the repository root. The
`plastprior/` subdirectory is the Python package, not a separate workspace.

The current CSV and databases are in `result/`. Required frozen evidence is in
`result/figure_data/_dependencies/baseline/`. Generated images, figure tables, reviews, supplementary files
and presentations are under `result/`; plotting source remains under `FigureCode/`.
The former result directories and compatibility link are retired. See
[the result layout](results_layout.md) for exact locations and update behaviour.

Use `FigureCode/INDEX.md` and `FigureCode/SI_INDEX.md` to select figures. Fig. 3 and Fig. 4
retain their approvals. Pending reviews and frozen figures retain their previous
states. Five-level labels remain a figure-only interpretation; the data files,
scores, ranks and Top-N membership were not changed by relocation.

`FigureCode/managed_sources.json` pins the current rounded data;
`FigureCode/figure_sources.json` pins the required baseline. Original build records
remain unchanged with their assets. `result/figure_data/_metadata/manifest.json` records their relocation
and the code changes needed to read the new locations.

The sections below describe earlier workspace recovery operations. Their recorded
paths are historical evidence, not instructions to use or recreate old locations.

## Migration and recovery

Both working states, generated files and Git histories were backed up before merging in the sibling
`PlastPrior_backups/20261026_155412_before_merge/` directory. Original input data
and the shared Python environment were not changed. Backups use independent APFS
copy-on-write files, not hard links. This is a local rollback copy, not an off-device backup.

The former `missing-contribution-repair/PlastPrior` worktree was removed at the
user's request on 2026-10-26 after verification. Its final 1,066 regular files
and 14 symbolic links are preserved in
`audit_archive/worktree_retirement_20261026/snapshot/`, with a complete
`repository.bundle`, SHA-256 manifests and `RECOVERY.md` instructions alongside it.
The pre-merge backups and `codex/missing-contribution-repair` branch remain available.
The snapshot is recovery material, not an active Git checkout.

Before removal, all 85 formal output files and 56 figure output files matched
the canonical project byte for byte; all nine figure manifests and both formal
SQLite databases passed verification. After removal, 43,249 canonical files
matched their pre-removal hashes and all canonical symbolic links remained valid.
Only this workspace documentation and `AGENTS.md` were subsequently updated to
record the cleanup. No scores, rankings, Top-100 membership or figures were
regenerated. The neighboring Dashboard directories were not removed.
See `audit_archive/worktree_retirement_20261026/pre_removal_verification.json`
and `post_removal_verification.json` for the verification records.

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
.venv/bin/python FigureCode/verify_figures.py
Rscript FigureCode/tests/priority_policy.R
.venv/bin/python -m unittest discover -s tests
```

These checks do not regenerate scientific results. Future analysis runs are
separate operations and must follow the score/rank regression checks in the
delivery pipeline.
