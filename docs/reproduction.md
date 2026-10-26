# Reproduction and verification

> Current scoring-policy update: [zero-contribution policy](zero_contribution_policy.md)
> supersedes the complete-domain eligibility rule and its recorded 4,244/10,881
> verification counts below. Those dated results describe the earlier export,
> not the repaired candidate. Upstream evidence admission remains unchanged.


The implemented scope is reproduction from specified frozen inputs through
identity assembly, evidence integration, hazard/exposure assessment, ranking
and compact export. It does not rebuild live queries, VEGA predictions or all
raw-source transformations. See [data preparation](data_preparation.md) before
running. The code repository alone does not supply the required data.

## Environment

Use the installation commands in the [README](../README.md#installation), with
64-bit Python 3.12 and Git. The notebook kernel is named `plastprior` and displayed
as **PlastPrior (Python 3.12)**. Run Jupyter from the project environment and the
project root. RDKit must match the declared version and provide InChI support.

If environment activation is unavailable, invoke its Python directly:

```text
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, use `.venv\Scripts\python.exe` with the same arguments; in PowerShell,
the explicit executable path can be written `.\.venv\Scripts\python.exe`.
Use the same interpreter for kernel registration, tests and execution.

The last verified environment used Python 3.12.13, pandas 3.0.2, NumPy 2.5.4 and
RDKit 2026.3.1. Requirements pin direct packages and a GIC Git revision, but do
not fully lock transitive dependencies. NumPy is not explicitly pinned by the
current requirements. These observed versions are not a tested portable lock.
Native Windows and a fresh independent installation remain unverified.

## Output directories and execution

The Notebook uses `DATA_ROOT`, `RESULTS_DIR`, `ARCHIVE_DIR` and `KEEP_INTERMEDIATES`.
Its setup cell creates a unique `REPORT_DIR` under `audit_archive/<run>/work/`.
Do not set REPORT_DIR to results. Restart the kernel and execute all 17 code cells.
The final cell exports and verifies the complete archive, then publishes the daily pair.

Run the equivalent CLI from the project root:

```sh
python main.py --rank-priority --top-n 100 --require-supporting-inputs
```

Optional settings:

- `--data-root PATH`: the complete frozen input collection.
- `--output-dir PATH`: daily pair location, default `results`.
- `--archive-dir PATH`: separate archive root, default `audit_archive`.
- `--keep-intermediates`: retain successful stage files for stage-level checks.
- `--baseline-csv PATH`: explicitly compare previous publication values before publishing.

Relative data/output/archive paths resolve from the project root. Without ranking,
partial or inspection runs retain their workspaces and do not replace the daily pair.
Full runs automatically compare against an existing daily CSV. Differences in existing
scientific fields stop publication for investigation; family labels are separate annotations.

For unattended Notebook execution, keep its executed copy outside the daily folder:

```sh
mkdir -p audit_archive/notebook_execution
python -m jupyter nbconvert --execute --to notebook --ExecutePreprocessor.kernel_name=plastprior --ExecutePreprocessor.timeout=1800 --output PlastPrior.executed --output-dir audit_archive/notebook_execution PlastPrior.ipynb
```

The timeout is per cell. Export can take several minutes. Original frozen queries and
VEGA outputs are read; no live query or new VEGA prediction is invoked.

## Expected artifacts and resource use

```text
results/                              # POSIX directory link to verified daily pair
  PlastPrior_results.csv
  PlastPrior_dashboard.sqlite
audit_archive/<run>/
  work/                               # retained on failure or --keep-intermediates
  package/
    PlastPrior_results.sqlite         # full audit archive, for offline use
    PlastPrior_results.csv
    PlastPrior_data_dictionary.csv
    README.md
    dashboard/PlastPrior_dashboard.sqlite
    delivery_manifest.json
    daily/                            # two files exposed through results
```

The CSV has 60 publication fields. The small SQLite contains all final details,
family audit, embedded dictionary and interpretation guide. The complete archive
retains all 251 original final fields and retained intermediate evidence. Scores
and ranks remain independent of structural family annotations.

On POSIX, a single directory-link replacement switches both daily files together.
Existing physical results directories are preserved whole in `legacy-results-*`.
Windows users can call the cross-platform `export_results` on completed stage files;
atomic daily-link publication is currently POSIX-only. Native Windows end-to-end
execution remains unverified.

Successful managed workspaces are removed only after validation and publication.
Original source files and existing archives are retained. Stage data occupy several
GB and the full archive roughly 3 GB; peak storage exceeds the two visible daily files.
An earlier local full run took about 13 minutes. This is not a portable runtime guarantee.
See [output layout](results_layout.md) for recovery and preservation details.

## Verification

Three checks answer different questions:

| Check | What it establishes | Required inputs |
| --- | --- | --- |
| Fixture-based tests | Implemented policy boundaries and export invariants | Code and installed dependencies |
| Current-result reproduction | Agreement of rerun scores, ranks, source links and audit fields with a selected verified package | Exact frozen inputs and the selected reference package |
| Historical migration regression | Agreement within the explicitly documented legacy comparison scope | Frozen historical run/checkpoints plus current stage outputs and applicable inputs |

Run fixture-based tests from the project root:

```text
python -m unittest discover -s tests -v
```

Successful tests do not substitute for a full run. For the locally verified
frozen collection, expected analysis counts are:

| Measure | Expected value |
| --- | ---: |
| Final compounds | 15,125 |
| Ranking-eligible compounds | 4,244 |
| Inclusive Top-100 members | 107 |
| Unranked compounds | 10,881 |
| Model-identity-review compounds | 15 |
| Top-100 cutoff score | 19.5 |
| Boundary tie group | 22 |

Counts alone do not prove equivalence. Compare final fields by chemical key,
including missing values, valid zeros, eligibility, ties, Top-N membership and
source/exclusion flags. Also compare historical results and source memberships
when validating the complete final package. Keep recorded order where it is
part of the contract; do not round, fill missing values or silently reorder a
historical baseline to make a comparison pass.

For a rerun against the retained local package, the following read-only example
compares the final CSV and four primary SQLite tables. Set `candidate` to the
new export directory printed by the run. A public reference download is not
yet established, so the baseline must already be present locally.

```python
from contextlib import closing
from itertools import zip_longest
from pathlib import Path
import hashlib
import sqlite3

reference = Path("path-to-previous-publication-package")
candidate = Path("path-to-new-export-directory")

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def readonly(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection

from plastprior.delivery import compare_csv
compare_csv(reference / "PlastPrior_results.csv", candidate / "PlastPrior_results.csv")
with closing(readonly(reference / "PlastPrior_results.sqlite")) as old, closing(readonly(candidate / "PlastPrior_results.sqlite")) as new:
    for table in ("compounds", "historical_results", "source_records", "compound_memberships"):
        assert old.execute(f"PRAGMA table_info({table})").fetchall() == new.execute(f"PRAGMA table_info({table})").fetchall(), table
        query = f"SELECT * FROM {table} ORDER BY _row_number"
        for index, (left, right) in enumerate(zip_longest(old.execute(query), new.execute(query)), 1):
            assert left == right, (table, index)
print("Final CSV and primary-table comparisons passed.")
```

This example is a final-result comparison, not a repeat of every audit-body
comparison or an independent scientific validation. Exporter validation checks
all retained fields against the current run's stage files. For release evidence,
retain the run's input/environment identifiers and comparison reports as well.
Do not compare SQLite file hashes across independently created exports as the
sole equivalence criterion: export metadata can differ while scientific values
remain identical.

Historical regression additionally needs the separately supplied historical
run directory, including its manifests and checkpoints. For example, after a
fresh CLI run with `--keep-intermediates` and with that baseline available:

```text
python -m plastprior.validation --stage ranking --baseline "path to the frozen historical run" --results audit_archive/RUN_ID/work/stage7/7b --output-dir audit_archive/historical_check_01
```

Do not pass the compact SQLite file as `--baseline`. The validator expects a
historical run directory. That baseline is not included in Git, and the retained
audit scripts are records of earlier methods rather than portable launchers.

## Available evidence and remaining limits

The latest local full test executed all 17 code cells and compared 142 stage
artifact hashes, every final field and source association, CSV bytes and ranked
views with the selected baseline. All comparisons passed. Data and implementation
preservation were separately checked. These records predate the present
documentation edits; no scientific rerun is implied by this guide.

Retained reports are located through [local results storage](results_layout.md).
They remain local files excluded from Git, not a public archive. Earlier method
sections retain their historical test counts and environments; those observations
must not be presented as a new full-suite test on another system.

The 28.1% complete-case ranking, identity quarantine, GIC limitations, frozen
derived-input dependencies and unvalidated scientific assumptions constrain
interpretation. Public data access, distribution decisions, licensing/citation
metadata, a complete environment specification and independent macOS/Windows
installation checks remain release tasks. Exact computational agreement does
not resolve those limitations.
