# Daily results and audit archives

Use these two files together:

- `results/PlastPrior_results.csv`: 60 columns; one row per full InChIKey.
- `results/PlastPrior_dashboard.sqlite`: paired browser details, family evidence,
  embedded field dictionary and interpretation guide.

`results` is a directory symlink on POSIX, pointing to one verified run's `package/daily`.
The link is switched atomically, so CSV and SQLite always come from the same run.
The browser verifies the exact CSV SHA-256. Do not edit or re-save one member of a pair.
Native Windows atomic publication is not implemented; export_results still produces
an independently verified package and does not require symbolic links.

## Archives

`audit_archive/<run>/package/` retains the complete `PlastPrior_results.sqlite`,
publication CSV, browser database, readable dictionary and README, and delivery
manifest. Daily files are hard links when supported, avoiding duplicate database
storage. Treat generated files as read-only; edit a separate copy for analysis.

The full archive preserves all 251 original compound fields, historical results,
source memberships and retained intermediate evidence under the compact-v2 contract.
`chemical_family_audit` adds per-compound structural annotations separately.
`run_metadata.chemical_families` records rules, version, RDKit version and coverage.
Original source input bytes remain in `data/`; the audit database does not contain
all original input files or original stage-file bytes.

Pre-existing `results` directories are moved whole into `audit_archive/legacy-results-*`.
The migration record maps their old and new root paths; files are not deleted or
rewritten. Historical logs retain their original paths. Earlier audit artifacts and
online verification evidence remain in that preserved directory tree.

## Running

```sh
python main.py --rank-priority --require-supporting-inputs
```

Both CLI and Notebook create a fresh `audit_archive/<run>/work` directory. Successful
runs export and validate the archive, compare existing publication values with the
previous daily CSV, publish the pair, and remove temporary stage files. Failures keep
the old daily pair and retain their workspace. `--keep-intermediates` (Notebook:
`KEEP_INTERMEDIATES=True`) preserves stage files for partial-stage investigation.
`--baseline-csv PATH` can supply an explicit regression baseline. A scientific change
stops publication for investigation; family labels alone may differ.

If a run fails after export, its package and any delivery manifest remain available;
inspect the recorded state before retrying. Run archives are never automatically pruned.
The complete rerun has a multi-gigabyte working peak even though only two files are
visible in results. These artifacts and archives are ignored by Git.
