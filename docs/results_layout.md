# Retained results and verification records

The user-approved local cleanup retains one verified compact result package and
the evidence needed to review its execution, storage migration and historical
comparisons. This is a storage and documentation change, not a scientific rerun
or a resolution of outstanding identity, GIC or source-access questions.

## Final files

The selected run is `20261023T191130Z-0fa717ee`:

- [Final CSV](../results/final/20261023T191130Z-0fa717ee/PlastPrior_results.csv):
  15,125 records and 53 summary fields; 12,801,513 bytes.
- [Final SQLite](../results/final/20261023T191130Z-0fa717ee/PlastPrior_results.sqlite):
  all 251 final fields, historical final results, source links and retained audit
  records; schema 2; 3,302,772,736 bytes.

CSV SHA-256: `2c803231c04ad8dc215cebcc26150e1ade020486197d4926b981ddd10c295376`.

SQLite SHA-256: `9515eca926145898b13c0b3e33237b2fd53361f381015b34759916171d414742`.

Start with the CSV for routine use. SQLite views `eligible_ranking`,
`top_priority` and `unranked_review` contain 4,244, 107 and 10,881 records,
respectively. `compounds` provides the complete final fields. Missing scores
are not zero, and lack of a rank does not establish low risk.

## Retained verification evidence

| Directory under `results/verification/` | Retained evidence |
| --- | --- |
| `notebook_run/` | Full 17-cell executed notebook, test method, execution log, exact comparison report, pre-run hashes and preservation checks |
| `compact_export/` | Schema-1 versus schema-2 field comparisons, export verification, baseline hashes and methods |
| `historical_regression/` | Complete Stage 7B validation chain, including all upstream historical comparisons and exclusions |
| `publication_review/` | Source inventories, official workbook candidates, provenance evidence and workbook comparison methods/reports |
| `previous_notebook/` | Earlier notebook comparison and preservation JSON records |
| `previous_export/` | Earlier export verification JSON |
| `cleanup/` | File migration/deletion manifest, cleanup method, logs and final integrity report |

Useful entry points:

- [Executed notebook](../results/verification/notebook_run/PlastPrior.executed.ipynb)
- [Latest notebook comparison](../results/verification/notebook_run/comparison_summary.json)
- [Storage migration verification](../results/verification/compact_export/verification.json)
- [Historical ranking validation](../results/verification/historical_regression/ranking_validation_summary.json)
- [Workbook verification](../results/verification/publication_review/workbook_comparison/verification.json)
- [Migration manifest](../results/verification/cleanup/migration_manifest.json)
- [Cleanup integrity report](../results/verification/cleanup/cleanup_report.json)

The retained original files are copied without modifying their bytes. Paths in
their recorded execution output, hashes and historical reports therefore retain
their original meaning. The migration manifest maps each inventoried original
path to its current destination or an explicit deletion disposition, with its
original byte size and SHA-256. Audit scripts are retained as records of methods;
they are not automatically rerunnable from their relocated directories, and
some compare baselines that have now been removed.

The three machine-readable documents in `docs/` include a separate
`result_storage_update` annotation. Relocated evidence references identify their
current location and retain the original path. Historical stage-output entries
continue to describe the original files; their storage annotations point to
the corresponding SQLite artifact. No old file hash is presented as the hash of
a different notebook, a reconstructed CSV or the entire SQLite database.

## What cleanup changes

Superseded databases, duplicate notebook/CLI runs, standalone stage outputs,
older validation copies, HTML exports, temporary kernels and routine logs were
selected for removal after retained copies passed byte-level verification.
The selected collection contains 91 original files, approximately 3.43 GB,
plus the small new cleanup records. Approximately 37.53 GB of duplicate and
temporary content is removed; actual filesystem space recovery may differ.

The raw `data/` collection, source notebook, algorithms, configuration and tests
are outside the cleanup deletion scope. No scoring or ranking stage is executed.
The input collection is checked against the latest successful notebook run;
implementation files are fingerprinted before and after cleanup.

The compact database retains parsed stage records according to its documented
retention policy, not all original CSV/JSONL file bytes. Explicit out-of-universe
patent-reference bodies are omitted with recorded coverage and reasons. Deleted
old database files cannot be used for a new direct comparison; the completed
comparisons and their fingerprints remain available.

## Running again

The default notebook still writes intermediate outputs to `results/stage*` and
a new final package to `results/final/<new_run_id>/`. Cleanup is not automatic.
After removal of stage files, run the full notebook before attempting a
partial-stage run or calling `export_results()` again. The final SQLite alone
is not an input directory for that exporter. Viewing the retained results needs
no rerun. Retained historical regression reports and source-access evidence
remain distinct from a successful current notebook execution.

These local artifacts remain excluded from Git. This layout records local
retention and does not declare permission to publish the data or evidence files.
