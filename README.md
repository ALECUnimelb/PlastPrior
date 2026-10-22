# PlastPrior

PlastPrior is being developed as a framework integrating hazard and exposure
evidence to prioritise plastic-associated chemicals. The current implementation
is limited to local input inspection. It does not standardise chemical
identifiers, combine inventories, or calculate hazard, exposure, or priority scores.

## Input inspection

`plastprior/inputs.py` is the single implementation used by `main.py` and
`PlastPrior.ipynb`. It reads the 12 declared source files, checks the required
column labels, and reports dimensions for 14 selected source-native tables:
two identity-reference tables, 11 inventory tables, and one literature-to-chemical
link table. The catalog is `plastprior/sources.json`.

The notebook contains Setup and Stage 1. It displays file versions and dates,
table dimensions, and inspection outcomes. Full provenance notes, references,
and observed SHA-256 fingerprints are saved in the inspection reports.
Versions, dates, and references are recorded provenance, not an independent
verification against the publisher's latest release. Unrecorded metadata is
shown as **Not recorded**. File modification times are not treated as source dates.

The initial file declarations, provenance notes, and worksheet/header selections
were carried forward from the ChemicalPrio input registry and readers. They were
checked against the local frozen input collection. No legacy runtime code or
scoring implementation is imported.

## Project structure

```text
PlastPrior/
  main.py
  PlastPrior.ipynb
  plastprior/
    inputs.py
    sources.json
  tests/
    test_inputs.py
  data/                     # Local inputs; ignored by Git
  results/                  # Generated reports; ignored by Git
```

The `plastprior` package holds the scientific implementation. The command line
and root-level notebook use the same functions. Tests are versioned source code;
their temporary fixtures do not require or alter the research collection.

The planned sequence is input validation and ingestion, chemical identity
resolution, QSAR evidence integration, evidence assembly, hazard assessment,
exposure assessment, and chemical prioritisation. Only the source-inspection
part of Stage 1 is implemented. Standardised source records and subsequent
stages will be introduced incrementally with corresponding validation.

## Installation

Use 64-bit Python 3.12. From the project directory, create an isolated environment:

```text
python -m venv .venv
```

Activate it on macOS:

```sh
source .venv/bin/activate
```

On Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then install the dependencies and register a kernel inside this environment:

```text
python -m pip install -r requirements.txt
python -m ipykernel install --sys-prefix --name plastprior --display-name "PlastPrior (Python 3.12)"
```

If activation is unavailable, invoke the environment's interpreter directly:
`.venv/bin/python` on macOS or `.venv\Scripts\python.exe` on Windows. The same
`-m pip`, `main.py`, and `-m jupyterlab` arguments apply. No system policy change
is required. This stage uses pandas, openpyxl for XLSX, and xlrd for legacy XLS;
R, RDKit, and the VEGA application are not required for input inspection.

## Local data

The input collection is not included in Git. Obtain the frozen files through
the project's authorised data-sharing arrangements and preserve this layout:

```text
data/
  SourceDatabase/
  Vega output/
  GIC Regulatory Inventory/
  Patent data/
  Literature data/
  Official_Production_Volume_Data/
```

Exact source filenames and worksheet selections are listed in `sources.json`.
Relative `data_root` paths resolve from the project root. An absolute path may
be supplied for an external collection. Inputs are read without being modified;
there is no automatic download, conversion, or repair of a missing source.

The five supporting groups receive **presence checks only**. The checks require
20 named VEGA reports, named GIC/patent/literature files, and the production
manifest plus its eight source directories. They do not certify report contents,
all nested production files, or readiness for a future scoring workflow. The
recursive file totals include any supplementary backups present in those folders.
Missing supporting inputs are reported separately from Stage 1 source failures.
Each later stage must validate the auxiliary inputs it actually uses before
performing its calculations.

## Run

Command line, on macOS or Windows:

```text
python main.py
python main.py --data-root "path to an external data directory"
python main.py --require-supporting-inputs
```

A missing source file, unreadable source table, absent required column, or empty
selected table produces a non-zero exit status. By default, missing auxiliary
items remain visible but do not fail Stage 1. Add `--require-supporting-inputs`
to also return a non-zero exit status for failed auxiliary presence checks;
this option does not validate auxiliary contents. Version metadata gaps are
reported but are not treated as unreadable data.

Both interfaces save the full inspection reports, including failure details:

| File | Contents |
| --- | --- |
| `results/source_inventory.csv` | Source metadata, references, observed hashes and file status |
| `results/table_dimensions.csv` | Selected sheets, header rows, dimensions, warnings and table status |
| `results/supporting_inputs.csv` | Auxiliary item presence, local file totals and missing-item details |

Reports are UTF-8 CSV files and are replaced on each run. The command line accepts
`--output-dir` to retain reports in a separate directory; relative paths resolve
from the project root. The notebook exposes `REPORT_DIR` for the same purpose.
The API distinguishes `sources_passed` (Stage 1) from `supporting_present`
(auxiliary presence). `passed` and `require_complete()` retain the combined
check, while `require_sources()` enforces the Stage 1 boundary.

For an interactive review:

```text
python -m jupyterlab
```

Open `PlastPrior.ipynb` from the project directory and select **PlastPrior
(Python 3.12)**. Restart the kernel and run all cells in order. The source
notebook is stored without outputs; executed copies and HTML reading versions
belong in the ignored `results` directory:

```text
python -m jupyter nbconvert --execute --to notebook --ExecutePreprocessor.timeout=600 --output-dir results PlastPrior.ipynb
python -m jupyter nbconvert --to html --output-dir results results/PlastPrior.ipynb
```

Large inputs can take several minutes to inspect. CSV tables are processed in
chunks; selected Excel worksheets are loaded one at a time.

## Interpretation and verification

- **Parsed rows** are data rows returned by the declared reader after the
  selected header. pandas omits blank physical lines in CSV inputs and may omit
  trailing empty worksheet rows.
- **Non-empty rows** have at least one cell that is neither missing nor an empty
  or whitespace-only string. This is a table-level diagnostic, not a chemical
  identifier validity check.
- Rows may contain duplicates, unresolvable identifiers, or non-chemical entries.
  Do not sum row counts across sources or interpret them as unique chemicals.
- Source-native values and column labels are preserved. Literal strings such as
  `NA` are not silently converted into missing values. Descriptive output and
  project documentation are in English; original source data are not translated.
- SHA-256 identifies the inspected file bytes. A fingerprint alone does not
  establish scientific validity, licensing permission, or an independently
  authenticated source version.
- Required labels provide a basic schema check; this is not a complete validation
  of every field, unit, identifier, formula, or external link in a workbook.
- Workbook-reader warnings are retained in the table report. Unsupported Excel
  formatting extensions are not interpreted; the original files are not saved
  or modified. Formula results rely on values cached in the supplied workbook;
  formulas are not recalculated.

Run tests without the research collection:

```text
python -m unittest discover -s tests -v
```

Direct dependencies are pinned in `requirements.txt`; transitive dependencies
are not fully locked. Native Windows execution must be verified separately
before claiming cross-platform validation.

For publication, archive the selected input fingerprints, exact environment,
code revision, executed notebook and corresponding results as a fixed release.
The ignored `results` folder is a local working directory, not a publication
archive. Source versions and acquisition instructions still require review;
unknown historical metadata must remain explicitly unrecorded until supported
by evidence. Structural migration and changes to scientific rules should be
reviewed separately, with stage-level comparisons against a documented
reference input/result pair.
