# Reproduction and verification

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

## Choose an output directory

Use a new directory for each independent run. Existing stage files within a
reused directory can be replaced. The final exporter alone guarantees a new
`final/<run_id>/` directory and refuses an existing explicit destination.

The source notebook defaults to `DATA_ROOT = Path("data")` and
`REPORT_DIR = Path("results")`. For a separate Notebook run, change only these
configuration values as needed; for example:

```python
DATA_ROOT = Path("data")
REPORT_DIR = Path("results") / "reproduction_nb_01"
```

Choose another suffix if that directory already exists. The notebook requires
the project root as its working directory. Command-line paths resolve from the
project root; absolute paths are also accepted for an external input collection.

## Execute all stages

**Interactive Notebook:** launch `python -m jupyterlab`, open `PlastPrior.ipynb`,
select the project kernel, set an unused `REPORT_DIR`, restart the kernel and
run all cells in order. There are 17 code cells, including final export. Do not
skip directly to export after intermediate files have been cleaned up.

**Unattended Notebook:** first set `REPORT_DIR` in the notebook configuration as
described above. The following commands assume `results/reproduction_nb_01` is
the selected directory. They save an executed copy and an optional HTML view:

```text
python -m jupyter nbconvert --execute --to notebook --ExecutePreprocessor.kernel_name=plastprior --ExecutePreprocessor.timeout=1800 --output PlastPrior.executed --output-dir results/reproduction_nb_01 PlastPrior.ipynb
python -m jupyter nbconvert --to html --output PlastPrior --output-dir results/reproduction_nb_01 results/reproduction_nb_01/PlastPrior.executed.ipynb
```

`--output-dir` here controls the executed Notebook/HTML location; it does not
override the pipeline's `REPORT_DIR`. The timeout is **per code cell**. The last
verified export cell took approximately 436 seconds; allow more time on slower
machines rather than interpreting a timeout as a scientific mismatch. The
example timeout is a configurable execution allowance, not a runtime guarantee.

**Command line:** run the full pipeline into a separate directory:

```text
python main.py --rank-priority --top-n 100 --require-supporting-inputs --output-dir results/reproduction_cli_01
```

The ranking flag enables prerequisite stages automatically. `python main.py`
without a stage flag performs input inspection only. No live source queries or
VEGA calculation are invoked by either full-run interface.

The seven scientific stages are input inspection, identity assembly, QSAR/
Pov-LRTP integration, evidence assembly, hazard assessment, exposure assessment,
and prioritisation/ranking. Lettered subdivisions describe evidence boundaries
within those stages. [Methods](methods.md) documents individual stage commands.

## Expected artifacts and resource use

The complete run writes inspection reports, stage files and a final package:

```text
<REPORT_DIR>/
  source_inventory.csv
  table_dimensions.csv
  supporting_inputs.csv
  stage2/ ... stage7/
  final/<run_id>/
    PlastPrior_results.csv
    PlastPrior_results.sqlite
```

The final cell prints paths and a verification summary. The two final files are
published only after the exporter validates retained records, field values,
references, ranking selections and source-file preservation. SQLite stores all
251 final fields for the verified collection; CSV provides 53 summary fields.

The last local test took about 13 minutes including independent comparisons and
file-preservation checks. Stage outputs were about 5.87 GB, and the final files
about 3.32 GB, excluding inputs, journals and other temporary files. Plan for
more than this combined output size in free space. Peak memory requirements
have not been established across machines; do not interpret these observations
as minimum hardware specifications. Each full run creates stage outputs again.

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

reference = Path("results") / "final" / "20261023T191130Z-0fa717ee"
candidate = Path("path-to-new-export-directory")

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def readonly(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection

assert digest(reference / "PlastPrior_results.csv") == digest(candidate / "PlastPrior_results.csv")
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
fresh CLI run and with that baseline available:

```text
python -m plastprior.validation --stage ranking --baseline "path to the frozen historical run" --results results/reproduction_cli_01/stage7/7b --output-dir results/historical_check_01
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
