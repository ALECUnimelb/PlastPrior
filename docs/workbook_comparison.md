# Frozen and official workbook comparison

Current local storage: see [retained results and verification records](results_layout.md). Evidence files were relocated without changing their bytes. Historical paths and removed stage-output locations are documented in the migration manifest; the review findings below remain unchanged.

Review date: **23 October 2026 (Australia/Melbourne)**.
Code and source-register baseline: `9877513`.

**No differences were found in the stored scientific cell values, formula
content, or fields read by the current pipeline across the four workbook pairs.**
The files remain different at the byte level. The observed differences concern
presentation, localized application text and file metadata. The cause and date
of the historical edits cannot be established from this comparison alone.

The [machine-readable comparison](workbook_comparison.json) contains results for
all 23 worksheets, per-field fingerprints for the five declared input tables,
reader versions, code references and local evidence-artifact hashes. This report
follows the [source access review](data_access_review.md). It does not replace
any frozen input or change source licence and access decisions.

## Findings by workbook

| Source | Worksheets checked | Scientific values and stored formulas | Presentation and metadata differences |
| --- | ---: | --- | --- |
| PlastChem 1.01 | 11 | No differences | 110 resolved cell-style differences in `Full database`, including one additional explicitly stored blank cell; added font/fill/style definitions and person metadata; save, window and selection metadata changed |
| MPLEACH | 1 | No differences | Font/style changes affecting 19,297 cells, column widths, default layout, view and save metadata; custom number-format identifiers were remapped without changing parsed values |
| LitChemPlast | 7 | No differences | Exactly 25 file bytes differ: 17 inside the BIFF `WRITEACCESS` record and 8 in the compound-file root modification timestamp; all other Workbook-stream bytes and both document-property streams are identical |
| FCCprio 0.2 | 4 | No differences | Three cell-style differences, layout/view/save metadata, custom XML member reordering, localized compatibility text in five legacy comment representations, and embedded logo pixels |

The PlastChem blank-cell difference does not add a scientific observation.
Both input readers return the same table extent. Cell-style counts refer to
resolved style comparisons, not changed chemical records.

For FCCprio, the five comment bodies and author lists are unchanged after
separating the explicitly identified application wrapper and labels. The
localized wrapper is not a change to a scientific annotation. Custom XML payloads
are identical as a multiset despite their member ordering. Merged ranges are
also identical after order normalization. The embedded image is a Food Packaging
Forum logo in both files: 349 of its 602 × 226 RGBA pixels differ. Visual inspection
found the same logo; no pixel-identity claim is made. The logo is not read by the
scientific pipeline.

The three XLSX workbooks contain **2,017 formula cells** with identical stored
formula XML and cached values. In the XLS workbook, **82,572 BIFF formula records**
are identical because the only changed Workbook-stream record is `WRITEACCESS`.
No formula was evaluated, refreshed or saved during this audit.

## Fields consumed by the pipeline

Every column in the five declared tables was compared, including columns not
selected for a derived evidence field. Row order and column order were preserved.

| Workbook / worksheet | Excel header row | Parsed data rows | Columns | Comparison |
| --- | ---: | ---: | ---: | --- |
| PlastChem / `Full database` | 2 | 17,932 | 231 | All fields equal |
| MPLEACH / `Table 1` | 1 | 838 | 23 | All fields equal |
| FCCprio / `FCCprio Tiers and Materials` | 12 | 1,222 | 42 | All fields equal |
| LitChemPlast / `Chemical` | 1 | 3,705 | 23 | All fields equal |
| LitChemPlast / `LiteratureChemical` | 1 | 65,535 | 18 | All fields equal |

These tables comprise **337 fields and 5,477,735 table positions per reader
policy**. They were checked under both existing policies: source preservation
(`dtype=object`, `keep_default_na=False`) and evidence inference (default type
inference and missing-value recognition). Comparisons cover dimensions, labels,
column types, index/order and typed values, including missing values and valid
zeros. They do not trim text, reorder records, round numbers or fill missing
values to obtain agreement.

The raw worksheet extents can exceed the parsed table dimensions because of
header rows or formatted trailing blanks. Both representations were checked;
this distinction is not a lost-record difference between the two files.

The relevant code paths are:

- [Source readers](../plastprior/inputs.py), `_read_options` and `_read_table`:
  declared sheets, header offsets, parser choice and source-preservation policy.
- [Identity references](../plastprior/identity.py), `_load_references`: consumes
  the declared PlastChem identity-reference fields.
- [Base evidence](../plastprior/evidence.py), `_load_tables`: consumes the declared
  tables under the evidence reader policy and checks source fingerprints.
- [Specialist evidence](../plastprior/evidence_specialists.py),
  `_load_specialist_tables`: reads LitChemPlast chemical/link fields and checks
  their source provenance.
- [Source declarations](../plastprior/sources.json),
  [base mappings](../plastprior/evidence_fields.json) and
  [specialist mappings](../plastprior/evidence_specialists.json): specify fields
  used in identity, evidence matching and subsequent evidence extraction.

The JSON comparison associates each compared field with these declared roles
and the existing Stage 4 field/match mapping exports. An empty role list does
not mean a field is absent from retained raw-row evidence. All columns were
compared regardless of role.

## Effect on current results

1. **Existing results are unchanged.** No input was replaced and no algorithm,
   policy, notebook, formula, evidence aggregation, score or ranking was rerun.
   Pre/post hashes cover all eight compared workbooks. All **142 existing stage
   outputs** also match their previously recorded SHA-256 fingerprints.
2. **No scientific input difference was found that would explain a change in
   current scores or ranks.** This conclusion follows from equal parsed input
   tables and unchanged code. It is not a claim that a replacement run was
   executed or that identical data independently validate the scientific method.
3. **The files are not interchangeable for provenance checks.** Replacing a
   workbook would change its SHA-256, source manifests and downstream provenance
   references. Existing consistency guards could reject a mixture of old and new
   stage artifacts even when scientific values agree. Those guards remain intact.
4. **The scientific exceptions remain unchanged.** The fifteen model-identity
   anomalies, GIC association flags, exposure eligibility and missing-value rules
   receive no new resolution from this workbook audit.

## Method, scope and remaining provenance work

The comparison reads local files and the already downloaded, publisher-checksummed
official candidates. Their identities and download links are retained in the
[source register](data_access_register.json). XML comparison resolves shared
strings and equivalent numeric serialization while preserving cell types,
positions, cached results and formula structures. XLS comparison checks all
parsed cells and the underlying OLE/BIFF streams. Presentation and metadata are
reviewed separately, rather than inferred from a file-level hash difference.

The independent audit reader uses Python 3.12.14, pandas 2.2.3, openpyxl 3.1.5
and xlrd 2.0.2. A supplementary read-only check uses the project's installed
reader dependencies, including pandas 3.0.2, under the bundled Python interpreter.
The exact versions and outcomes of both checks are retained in the JSON report.
No project build or scoring function is called by either reader check. Native
Excel recalculation and exhaustive visual-layout equivalence are outside scope.

The evidence supports describing the frozen local workbooks as **byte-different
copies with equivalent stored scientific tables relative to the identified
official candidates**. It does not establish who saved them, when they were
originally acquired, or a complete editing history. Save timestamps must not be
used as acquisition dates, and exact-byte mismatches remain visible in the register.

The practical next step is to retain the current frozen inputs and attach this
equivalence record to their provenance. Continue the unresolved source-access,
attribution and distribution review. Any future adoption of publisher originals
should be a separately approved input revision with new manifests and validation,
not an overwrite of this historical baseline.
