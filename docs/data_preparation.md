# Data preparation

This guide describes the frozen inputs required by the implemented workflow.
It is a file-preparation specification, not a public download service or a
statement that redistribution has been approved. Exact acquisition routes and
distribution decisions remain unresolved in the [source register](data_access_register.json).
If the complete frozen collection is unavailable, a code clone alone cannot
reproduce the reported scores and ranks. No replacement datasets are implied.

## Required layout

Place inputs under the project `data/` directory, or supply another data root.
Preserve spaces, filename case, worksheet names and manifest-relative paths.

```text
data/
  SourceDatabase/                         # 12 primary source files
  Vega output/                            # 20 frozen report files
  GIC Regulatory Inventory/               # Inventory and metadata
  Patent data/                            # Frozen patent query output
  Literature data/                        # Frozen PubMed query output
  Official_Production_Volume_Data/         # Manifests and referenced source files
  ExposureReference/
    20261006T233429Z/                      # Eight frozen derived/provenance files
```

The top-level source catalog is [plastprior/sources.json](../plastprior/sources.json).
The following lists describe requirements; source versions and dates are recorded
metadata, not independently certified release information.

## Primary sources

All files below belong in `SourceDatabase/`. Sheet names, header rows, source
roles, required columns and citation references are declared in the catalog.

| Source | Exact local filename |
| --- | --- |
| NORMAN SusDat | `susdat_2025-06-03-092022 (1).xlsx` |
| PubChemLite | `PubChemLite.csv` |
| PlastChem | `plastchem_db_v1.01.xlsx` |
| UNEP | `UNEP 2023.xlsx` |
| NORMAN MPLEACH | `MPLEACH.xlsx` |
| FCCmigex | `FCCmigex.xlsx` |
| FCChumon | `FCChumon.xlsx` |
| FCCprio | `FCCprio-List-v0-2-Zenodo-20260115.xlsx` |
| LitChemPlast | `LitChemPlast.xls` |
| ICCA | `icca_chemicals.csv` |
| UCSF | `UCSF paper database.xlsx` |
| PlasticMAP | `PlasticMAP_S1_210611.xlsx` |

Recorded file hashes and access evidence are in the source register. Six sources
lack a recorded version and nine lack a recorded snapshot date in the catalog.
Do not infer acquisition dates from file modification times. The four official
workbook candidates reviewed in the [workbook comparison](workbook_comparison.md)
have equivalent stored scientific tables but different file bytes. They must
not be silently substituted into this fingerprinted frozen run.

## Supporting evidence

| Folder | Required contents and authoritative declaration |
| --- | --- |
| `Vega output/` | All 20 report filenames in `sources.json` → `supporting_inputs`; exact report hashes, model versions and layouts in [qsar_models.json](../plastprior/qsar_models.json) |
| `GIC Regulatory Inventory/` | `inventory_20260330.jsonl` and `gic_list_tag_metadata.csv`; pinned input declarations in [evidence_annotations.json](../plastprior/evidence_annotations.json) |
| `Patent data/` | `pubchem_zero_patent_check_final.csv` |
| `Literature data/` | `pubmed_title_abstract_counts_final.csv` |

The 20 VEGA reports are frozen prediction outputs. Stage 3A regenerates and
checks the expected structure batch before associating report rows; it does not
execute VEGA or treat reported structures as authoritative identity repairs.
Report provenance is retained, while application-generation provenance remains
limited. Patent and PubMed files preserve query outcomes, including failures
and valid zeros. Repeating live queries is not guaranteed to reproduce the frozen
snapshot.

## Production and market files

`Official_Production_Volume_Data/` requires `source_manifest.json` and these
source directories:

```text
01_US_EPA_CDR/
02_ECHA_REACH/
03_Nordic_SPIN/
04_Japan_METI_CSCL/
05_South_Korea_Chemical_Statistics/
06_Canada_CEPA_Section71/
07_South_Korea_New_Chemicals/
08_Taiwan_Toxic_Chemicals/
```

Preserve the nested files referenced by the source and frozen input manifests.
Directory presence alone is insufficient: Stage 6A checks referenced raw-file
paths and hashes. A minimal distributable raw-file subset has not been approved;
neither the full local file count nor the presence of backup files defines such
a subset. File inventories and access limitations are documented in the
[data access review](data_access_review.md#supporting-and-production-evidence).

## Frozen exposure reference bundle

All eight files below belong in `ExposureReference/20261006T233429Z/`.
This bundle is required in addition to the primary and supporting source files.

| File | Role |
| --- | --- |
| `market_presence_evidence.csv` | Frozen derived market observations |
| `production_volume_evidence.csv` | Frozen derived production observations |
| `source_registry.csv` | Source definitions used by the frozen transformation |
| `input_manifest.csv` | Canonical production/market input inventory |
| `run_manifest.json` | Historical run provenance |
| `input_manifest.json` | Historical run input fingerprints |
| `stage6_checkpoint.json` | Frozen Stage 6 artifact membership and hashes |
| `official_us_epa_production_by_cas.csv` | Frozen official-production reference used in Stage 6B |

The first seven files and their hashes are declared in
[exposure_inputs.json](../plastprior/exposure_inputs.json). The eighth is declared
in [exposure_policy.json](../plastprior/exposure_policy.json) → `official_reference`.
These are historical derived tables and provenance records; their raw-source
transformations are not rerun by the current pipeline. Keep JSON and CSV
manifests separate. The application does not import the old project at runtime,
but an exact frozen bundle must be obtained separately.

## Preparation checks

1. Obtain the declared files through an approved route. Where a route remains
   unavailable, record the gap rather than filling it with a newer release.
2. Preserve the declared layout and check available SHA-256 fingerprints against
   the catalog-linked register and stage policies. A matching hash identifies
   bytes; it does not authenticate provenance or establish permission to share.
3. Run the initial inspection from the project root:

   ```text
   python main.py --require-supporting-inputs --output-dir result
   ```

4. Review `source_inventory.csv`, `table_dimensions.csv` and
   `supporting_inputs.csv` in that output directory. Missing source files,
   unreadable tables, missing required columns or empty selected tables fail
   source inspection. The option also makes missing auxiliary items fail the
   initial check.
5. Proceed with a full run only after addressing reported input issues.
   Stage 1 auxiliary checks concern presence, not full content validation.
   The separately required exposure reference bundle is checked by later
   stages, so an initial pass alone does not certify full-run readiness.

If a later stage reports a fingerprint mismatch, check the identified input
and version. Do not edit the expected policy hash to make a different input pass.
Adopting new inputs requires a separate versioned analysis and validation.

## Access, citations and distribution

Consult the [current source-by-source distribution checklist](data_distribution_checklist.md)
for conditional public deposits, provider-acquisition routes and unresolved scopes.
Official licensing evidence and exact local-file readiness are separate.

The repository currently provides source references, file identities and known
limitations. It does not yet provide a complete approved input archive, an
established project data-request route, or a public result deposit. Dataset
references are not substitutes for precise acquisition instructions.

Before a formal release, record a verified acquisition or application route for
each required item, the applicable citation, version/date evidence, exact-file
hashes and distribution decision. Unknown historical metadata must remain
explicit. Code licensing and permission to distribute source-derived evidence
are separate release decisions; this documentation does not resolve either.
