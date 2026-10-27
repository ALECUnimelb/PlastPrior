# PlastPrior

## Rounded scoring update (2026-10-27)

Current rounded H/E scores, four-level labels and configurable Dashboard scenarios
are documented in [docs/rounded_scoring.md](docs/rounded_scoring.md). Use
`output/2026-10-27/` for the new CSV and paired SQLite files; the 2026-10-26
export and manuscript figures remain the frozen baseline.


PlastPrior integrates chemical identity, hazard and exposure evidence to
prioritise plastic-associated chemicals. It produces a CSV summary and a SQLite
database containing complete final results, source links and audit records.

**Status:** the seven-stage workflow and final export have passed a local full
Notebook run and comparison with frozen results. Public access to all exact
inputs, distribution decisions, code licensing and independent installation
validation remain incomplete. This repository alone is not a complete
reproduction package.

## Start here

For this local project, work in `/Users/ruiwang/Projects/APPs/PlastPrior`.
Current data are in `output/2026-10-26/`; current images and review decks are in
`Figure/`. See [workspace location and migration checks](docs/workspace_location.md).

| Purpose | Guide |
| --- | --- |
| Prepare the exact input collection | [Data preparation](docs/data_preparation.md) |
| Install, run and check results | [Reproduction guide](docs/reproduction.md) |
| Inspect scientific rules and stage-level evidence | [Methods and stage reference](docs/methods.md) |
| Locate the retained local CSV, SQLite and verification records | [Local results storage](docs/results_layout.md) |
| Review source distribution decisions | [Source-by-source checklist](docs/data_distribution_checklist.md) |
| Review source access and unresolved release requirements | [Data access review](docs/data_access_review.md) and [publication review](docs/publication_review.md) |

The local result links require the retained files on the reader's machine.
`data/` and `results/` are excluded from Git. A public result download or an
approved exact-input acquisition route has not yet been established.

## Installation

Use 64-bit Python 3.12 and Git. From the project directory:

```text
python -m venv .venv
```

Activate the environment using the command for your shell:

| Shell | Command |
| --- | --- |
| macOS | `source .venv/bin/activate` |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |

```text
python -m pip install -r requirements.txt
python -m ipykernel install --sys-prefix --name plastprior --display-name "PlastPrior (Python 3.12)"
```

Git is needed for the pinned Global Inventory Compiler dependency; the PyPI
package named `gic` is a different project. RDKit 2026.3.1 with InChI support is
required for identity processing. The workflow reads frozen VEGA reports and
does not run the VEGA application. See the reproduction guide for environment
limitations and commands that do not require shell activation.

## Prepare data

Follow the [complete input checklist](docs/data_preparation.md), including the
frozen `ExposureReference/20261006T233429Z/` bundle. Preserve filenames, table
layouts and manifest-referenced raw files. No automatic download or input repair
is implemented. Current online releases are not substitutes for the declared
frozen files.

An optional initial inspection is:

```text
python main.py --require-supporting-inputs --output-dir results/inspection
```

This inspects primary tables and auxiliary presence. It does not calculate
scores or verify every auxiliary file; later stages perform their own checks.
Without additional options, `python main.py` performs input inspection only.

## Run the complete workflow

Choose either interface; both call the same scientific modules.

**Notebook:** launch JupyterLab, open `PlastPrior.ipynb` from the project root,
select **PlastPrior (Python 3.12)**, restart the kernel and run all cells.

```text
python -m jupyterlab
```

The setup cell exposes `DATA_ROOT` and `REPORT_DIR`. To preserve earlier
intermediate files, set `REPORT_DIR` to a new directory, for example
`Path("results") / "reproduction_01"`.

**Command line:** the ranking option runs every prerequisite stage and final
export. Choose an unused output directory for each independent run.

```text
python main.py --rank-priority --top-n 100 --require-supporting-inputs --output-dir results/reproduction_01
```

Add `--data-root "path to the frozen data directory"` for external inputs.
Relative command-line data/output paths resolve from the project root.
The [reproduction guide](docs/reproduction.md) covers unattended Notebook
execution, comparison criteria and historical validation requirements.

The last locally verified run executed 17 code cells in about 13 minutes,
including comparison and preservation checks. Stage files occupied about
5.87 GB and the final package about 3.32 GB, before temporary files and inputs.
These are observations on the existing environment, not portable resource
guarantees. Allow additional disk space and time on other systems.

## Read the results

The last Notebook cell prints the daily pair and separate archive paths:

```text
results/                         # directory link switched after verification (POSIX)
  PlastPrior_results.csv
  PlastPrior_dashboard.sqlite
audit_archive/<run>/package/      # complete scientific archive and documentation
```

Stage files use `audit_archive/<run>/work/`. Successful temporary stages are removed
only after archive validation and pair publication; `--keep-intermediates` retains
them. Failed and partial runs retain their workspace. Existing physical results
folders are moved whole into the archive. See [output layout](docs/results_layout.md).

| File or SQLite view | Purpose |
| --- | --- |
| CSV | 60-field publication table, including structural family labels: identity, source memberships, selected evidence, scores, ranks and missingness |
| Data dictionary and README | Definitions, units, null conventions, policy, source tracing and usage |
| `PlastPrior_dashboard.sqlite` | Browser-sized projection of every final compound field, paired with the CSV by SHA-256 |
| `publication_results` | Exact text projection of the publication CSV in the full archive |
| `compounds` | All 251 final fields in the verified collection |
| `eligible_ranking` | Rankable assessments, including partial evidence with unavailable contributions counted as zero in sums |
| `top_priority` | Top-N including every boundary tie |
| `unranked_review` | Records with no available evidence and exclusion reasons |
| `source_records`, `compound_memberships`, `evidence` | Source and audit tracing |

For ranking queries, use `ORDER BY Priority_rank, inchikey`; SQL views do not
imply order. Missing numeric values use NULL and remain distinct from valid zero.
The compact database shares repeated audit bodies and stage values. Its
[storage contract and decoding helpers](docs/methods.md#final-results) explain
which parsed records can be reconstructed and which source bytes are external.

The repaired frozen-input analysis contains **15,125 compounds**, all rankable,
with **265 High**, **3,414 Moderate** and **11,446 Low** priority records under
`priority-hgt10-ege5-v1` (High: raw H>10 and E>=5).
**10,881 records remain marked Partial**; missingness does not cancel their
available contributions. The inclusive Top-100 has 100 compounds at a cutoff of 20 points; all 41
records tied at the boundary are retained.
See [the current scoring policy](docs/zero_contribution_policy.md).
Final directories are never overwritten by export. Temporary stages are cleaned only after verified publication; archives are retained.

For the updated ChemicalPrioDashboard, load `PlastPrior_results.csv` followed by
`PlastPrior_dashboard.sqlite` from the same export. The full archive
is for offline audit, not browser import. The display adapter preserves absent
formal scores and uses the selected literature source. The scientific archive
remains compact-v2; the separate publication and browser-detail contracts are
version 1. Publication field selection is defined in
`plastprior/publication_fields.json`, without rescoring or source enrichment.

## Scope and limitations

- The supported reproduction starts from specified frozen inputs. VEGA
  prediction generation, live database queries and some upstream production/
  market transformations are outside this workflow.
- Fifteen model-identity exceptions remain unresolved. Their QSAR and Pov/LRTP
  evidence is isolated; independent eligible evidence and source links remain.
- GIC name/identifier and metadata limitations remain visible. Associations
  are not confirmed identities or current regulatory determinations.
- Missing components contribute zero only in sums. Partial evidence remains
  rankable and visibly marked; zero-contribution or low-priority records do not
  establish low risk or safety.
- Scores are screening indicators. Agreement with historical computations
  does not independently validate the weights, thresholds, proxies or models.
- Direct dependencies are pinned, but the transitive environment is not fully
  locked. Native Windows and a fresh independent installation remain unverified.
- Source-access, citation and distribution decisions remain open. `LICENSE`,
  `CITATION.cff` and a versioned public research archive have not been established.

The [source register](docs/data_access_register.json) distinguishes recorded
metadata from unresolved provenance. The [workbook comparison](docs/workbook_comparison.md)
documents equivalent scientific tables in four checked pairs without treating
their different file hashes as interchangeable.

## Development and verification

The scientific implementation is in `plastprior/`; `main.py` and the root
Notebook provide interfaces. Source tests are retained in `tests/`.

```text
python -m unittest discover -s tests -v
```

These tests use local fixtures and do not require the research collection.
They do not replace a full frozen-input run. Exact field comparisons, input
fingerprints, execution records and the separate historical regression scope
are described in the [reproduction guide](docs/reproduction.md#verification).
