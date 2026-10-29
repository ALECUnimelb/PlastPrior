> Output-layout update: daily files are `results/PlastPrior_results.csv` and

> Current scoring-policy update: [zero-contribution policy](zero_contribution_policy.md)
> supersedes the complete-domain eligibility rule and its recorded 4,244/10,881
> verification counts below. Those dated results describe the earlier export,
> not the repaired candidate. Upstream evidence admission remains unchanged.

> `results/PlastPrior_dashboard.sqlite`. Complete archives and temporary stages are
> separate under `audit_archive/<run>/`. Stage-level paths in historical examples below
> refer to `<run>/work/`; retain them with `--keep-intermediates` when reproducing checks.
> See [output layout](results_layout.md) and [family classification](chemical_families.md).

# Methods and stage reference

This reference preserves the implemented scientific rules, field mappings,
selection and exclusion policies, output contracts and historical migration
checks. Start with the [README](../README.md), [data preparation](data_preparation.md)
and [reproduction guide](reproduction.md) for the current reader workflow.

All seven stages and compact final export are implemented. A statement that a
stage does not calculate downstream scores describes that stage's boundary,
not an unimplemented part of the complete pipeline. The subsection verification
counts and environment observations are records from their respective migration
steps; the current full-run evidence is summarised in the reproduction guide.

Commands assume the project root as the working directory. Generated stage paths
refer to fresh runs; the retained local verification collection has been relocated
as described in [results storage](results_layout.md). Historical comparison
commands require the separately supplied frozen historical run. They are not
standalone checks available from a clone of the code repository alone.

## Final results

After Stage 7B, the notebook and `python main.py --rank-priority` use the same
`plastprior.export.export_results()` function. Each successful export creates a
new directory under `results/final/<run_id>/`:

- `PlastPrior_results.csv`: a 60-field publication table, including incomplete
  and unranked records. Identity, source memberships, selected hazard pathways,
  exposure quantities/context, scores, ranks and missingness are explicit.
  Internal identity/GIC flags and detailed reasons remain in the archive.
- `PlastPrior_results.sqlite`: complete final analysis (all original fields),
  historical final results, source records and membership links, retained audit
  decisions, shared evidence bodies and sparse intermediate differences.
- `PlastPrior_data_dictionary.csv` and `README.md`: field meanings, source-field
  mapping, units, missingness, scoring policies and read-only access examples.
- `dashboard/PlastPrior_dashboard.sqlite`: all final compound fields plus display
  aliases, without the multi-million-row intermediate audit. CSV SHA-256 and row
  count bind this projection to the exact publication file. It is not a substitute
  for the complete archive.

The publication contract is `plastprior-publication-v1`; the detail projection
uses `plastprior-dashboard-v1`, independently of the archive schema. The
`publication_results` table reproduces the CSV text exactly. Production/market
metric, value status, jurisdiction and reporting period accompany its quantity.
Sources and missing dimensions are flattened without truncation; original JSON
and all source field text remain available in `compounds`. The export verifies
every publication field and every final field in the browser projection.

This is export schema **2**, `compact-v2`. It changes storage only. Scientific
stages, source files and prior output directories are not modified or deleted.
No evidence is merged merely because two sources report the same value.
The exporter does not migrate or overwrite an older schema-1 database.
The approved local retention cleanup removed superseded database copies after
verification; their hashes and comparison reports remain available.
See [retained results and verification records](results_layout.md) for
the selected final package, current paths and the migration manifest.

To package an existing completed run without recalculating scores, its complete
Stage 1–7 output collection must still be present:

```python
from pathlib import Path
from plastprior.export import export_results
package = export_results(Path("results"), progress=print)
print(package["csv"])
print(package["sqlite"])
```

An optional `output_dir` must name a new directory. Both files are published
only after validation, and existing destinations are never replaced. Intermediate
files remain available until an explicitly requested cleanup. Following the
current cleanup, read the retained final files directly; export-only execution
requires regenerated stage files. A full notebook run regenerates these files
and creates another final package. Original inputs are external to Git; approved access and distribution routes remain incomplete.

### Retention and storage

| Content | Compact representation |
| --- | --- |
| Final analysis, historical final order, source records and memberships | Complete primary tables, with field-by-field verification |
| Ranking, Top-N and unranked selections | SQL views over the final analysis |
| Explicitly declared intermediate compound tables | Column order, row order and final-compound references plus every unequal or otherwise absent field |
| CSV/JSONL evidence and decisions | Distinct source occurrences referencing shared, compressed record bodies; large repeated fields are interned separately |
| Historical/analysis differences | Original values and reasons retained; repeated large evidence text is referenced rather than copied |
| Stage 6A PubChemLite patent-reference rows outside the final compound universe | Full bodies omitted only when `eligible=False`, the sole reason is `outside_compound_universe`, and the key is outside the final collection; original row ranges, counts and an ordered omission digest retained |
| All in-scope candidates, invalid counts and query failures | Retained, including exclusions and selection reasons |
| Stage manifests, configuration, implementation and small text provenance | Embedded, with byte-level fingerprints |
| Whole-file backups of stage CSV/JSONL tables | Not embedded; original hashes remain inventoried |

Intermediate table factorisation is lossless at the **parsed-field and row-order**
level. It does not promise restoration of original CSV quoting or line endings.
For each intermediate record, fields equal to the final compound are referenced;
all different and stage-specific fields are retained as overrides. No field is
silently dropped. `compound_lexemes` preserves the original text of typed final
fields, so `0`, `0.0`, empty values and boolean strings can be reconstructed.
The patent-reference scope filter does not apply to identity-reference lookup,
other evidence sources or in-scope excluded records. Frozen historical scores
and all historical selections are preserved.

### Querying the database

Start with `results`, `eligible_ranking`, `top_priority` or `unranked_review`.
SQL views do not imply an ordering; use an explicit order:

```sql
SELECT * FROM top_priority ORDER BY Priority_rank, inchikey;
SELECT * FROM unranked_review ORDER BY inchikey;
SELECT artifact_path, record_number, source_id, record_id,
       audit_id, field_path, decision_reason, selected, payload_id
FROM evidence WHERE inchikey = 'FULL-INCHIKEY-HERE'
ORDER BY artifact_path, record_number;
SELECT path, disposition, record_count, retained_count, policy_json FROM artifacts;
```

`compounds` retains the complete final analysis. `historical_results` retains
historical results separately. `source_records` and `compound_memberships` provide
source-row traceability, with enforced foreign keys. Audit key lookup recognises
`inchikey`, `compound_key` and `Inchikey_std`; occurrence-level provenance remains
in each original record. Source-record identifiers and audit identifiers have
separate lookup columns. Records without a top-level compound key remain
accessible by artifact path and original record number.

`evidence` exposes searchable identifiers and decision summaries. Complete bodies
are stored in `evidence_payloads` as zlib-compressed canonical JSON, with explicit
references to shared field-name schemas and large values. Use the standard-library-backed helpers to
read complete records or reconstruct a factored intermediate table:

```python
import sqlite3
from plastprior.export import read_audit_payload, read_artifact_records, archived_bytes
with sqlite3.connect(package["sqlite"]) as connection:
    row = connection.execute("SELECT payload_id FROM evidence LIMIT 1").fetchone()
    record = read_audit_payload(connection, row[0])
    intermediate_rows = read_artifact_records(connection, "stage7/7a/compound_priority_assessment.csv")
    first_row = next(intermediate_rows)
    manifest = b"".join(archived_bytes(connection, "stage7/7b/ranking_manifest.json"))
```

`read_artifact_records()` yields retained rows in original order. For the scoped
patent-reference file it skips the explicitly omitted rows; `omitted_ranges`
records their original positions and reason. `archived_bytes()` supports embedded
provenance and the older schema-1 archives. It raises a clear error for compact
stage tables whose original bytes are not embedded. Ordinary SQLite clients can
query final results and audit lookup columns without custom extensions; decoding
complete compressed audit bodies requires the helper or the documented codec.

The field dictionary, manifests and embedded policies retain field meaning and
units. Declared final scores use REAL, ranks/counts use INTEGER, and boolean flags
use 1/0. Missing typed values use SQL NULL, while valid zeros are retained.
Other fields preserve original text. CSV keeps the exact original field text
and deterministic eligibility/rank/InChIKey ordering.

Validation covers every final and source field, CSV/SQLite agreement, every
retained audit field and lookup key, every reconstructed intermediate field,
omission ranges/counts/digest, shared-body fingerprints and references, ranking
order, ties, source links and database integrity. Inputs are fingerprinted again
at completion. SQLite binary hashes can differ across exports; compare logical
contents. Export does not authenticate inputs, resolve scientific exceptions or
establish redistribution permission.


## Input inspection

`plastprior/inputs.py` is the single implementation used by `main.py` and
`PlastPrior.ipynb`. It reads the 12 declared source files, checks the required
column labels, and reports dimensions for 14 selected source-native tables:
two identity-reference tables, 11 inventory tables, and one literature-to-chemical
link table. The catalog is `plastprior/sources.json`.

The notebook contains Setup, Stage 1, Stage 2 and Stage 3A/3B/4A/4B/4C/5A/5B/6A/6B/7A/7B, with seventeen code cells, including final export. It displays
file versions, table dimensions, inspection outcomes, source record counts,
identifier availability, identity-resolution outcomes, model coverage, QSAR
identity exceptions, historical LRTP calculation coverage, analysis exclusions, P/B/M/T dimension availability, exposure coverage and complete-domain priority tiers. Full provenance notes, references,
and observed SHA-256 fingerprints are saved in the inspection reports.
Versions, dates, and references are recorded provenance, not an independent
verification against the publisher's latest release. Unrecorded metadata is
shown as **Not recorded**. File modification times are not treated as source dates.

The initial file declarations, provenance notes, and worksheet/header selections
were carried forward from the ChemicalPrio input registry and readers. They were
checked against the local frozen input collection. The old project is never imported at runtime. Local historical kernels retain versioned source-function fingerprints for regression.


## Source record assembly

`build_source_records()` in `plastprior/inputs.py` assembles the 11 candidate
inventory tables using explicit `record_mapping` declarations in `plastprior/sources.json`.
PubChemLite and NORMAN SusDat remain identity references, and the LitChemPlast
literature-link table remains a relationship table. These three tables are listed
in the mapping report but are not read or appended by the assembly function;
Stage 1 inspects them separately. PlastChem contributes inventory records here
and supplies a separately mapped identity-reference table during resolution.

| Inventory table | Name | CAS | SMILES, in selection order | InChIKey | Native record identifier |
| --- | --- | --- | --- | --- | --- |
| PlastChem | `pubchem_name` | `cas` | `isomeric_smiles`, `canonical_smiles` | `inchikey` | `plastchem_ID` |
| UNEP | `Name` | `CASRN` | `SMILES` | `InChI_key` | Not declared |
| MPLEACH | `Compound_Name` | `CAS1` | `SMILES` | `InChIKey` | Not declared |
| FCCmigex | `Preferred_Name` | `CAS` | `SMILES` | `InChIKey` | Not declared |
| FCChumon S1/S2 | `Chemical name` | `CAS` | Not supplied | Not supplied | Not declared |
| FCCprio | `Chemical Name` | `CAS Number` | `SMILES` | Not supplied | Not declared |
| LitChemPlast | `PREFERRED_NAME` | `CASRN` | `SMILES` | `INCHIKEY` | `Chem_id` |
| ICCA | `Name` | `CASRN` | Not supplied | `InChIKey` | Not declared |
| UCSF | `PREFERRED_NAME` | `CASRN` | `SMILES` | `INCHIKEY` | Not declared |
| PlasticMAP | `Name` | `CASRN` | `SMILES` | `InChI_key` | `id` |

These mappings follow the historical source-selection fields. The first
available value in a declared field list is selected. A missing declared column
is an error, even if another fallback column is present; an empty mapping list
explicitly means that the source does not supply that field. Additional CAS
columns or alternative identifiers are not silently combined. Chemical
identifiers such as CAS and DTXSID are not assumed to be unique source-row IDs.

The versioned policy declares a case-sensitive missing-token list corresponding
to conventional tabular NA markers. For selection and availability only, values
are trimmed and compared with that list; actual null cells are also missing.
Literal `NA`, `N/A` and the other listed placeholders therefore remain in the
raw export but do not count as available identity values. This is separate from
Stage 1, whose non-empty counts describe occupied cells. Identifier syntax,
CAS checksums and chemical structures are not validated at this stage.

All inventory rows are retained. The historical MPLEACH inclusion rule requires
both reported InChIKey and SMILES; a missing required value sets `included=False`
and a field-specific `exclusion_reason`. Other inventories have no additional
identity-completeness gate at this stage. Included does not mean resolved or
chemically valid. Availability counts use **included records** as the denominator;
duplicates and excluded records remain individually traceable in the full export.

Each record retains:

- `record_id`: SHA-256 of the source ID, table ID, input-file SHA-256 and one-based
  parsed record number, encoded as a compact JSON array. It is stable for the
  same frozen file and table declaration; changes to file bytes change the IDs.
  It is a provenance key, not a chemical identifier or a cross-release identifier.
- `source_record_number`: position in the parsed table, assigned before filtering.
  `source_row_number` additionally identifies the physical Excel worksheet row,
  accounting for the declared header offset. It is absent for CSV because quoted
  multiline cells and skipped blank lines prevent a simple physical-line mapping.
- `source_native_id` and its column label, where explicitly declared. Native
  IDs may be missing or repeated; they are not used for deduplication.
- Four reported fields, their selected source columns and availability flags.
  Selected text is not trimmed, uppercased or chemically normalised. If no value
  is available, the selected field is empty; `reported_fields_json` retains all
  mapped raw values, including placeholders and unselected fallbacks. Values are
  textual representations of parsed cells, not Excel display formatting. The
  fingerprinted original file remains the authority for all other fields.

Assembly hashes each candidate source before and after reading and fails if the
bytes change. The manifest records source, catalog, implementation and exported
file hashes, the assembly policy and reader versions. A failed assembly does not
write a new report set; previously generated reports may still exist and must
not be treated as results of a failed run.


## Chemical identity resolution

`resolve_identities()` in `plastprior/identity.py` accepts the source assembly and
reads three frozen reference tables. `identity_reference_mapping` declarations
in `plastprior/sources.json` explicitly select their fields:

| Reference | Name | CAS | SMILES | InChIKey | Row inclusion |
| --- | --- | --- | --- | --- | --- |
| PubChemLite | `Synonym` | Not supplied | `SMILES` | `InChIKey` | All parsed rows |
| PlastChem | `pubchem_name` | `cas` | `isomeric_smiles` | `inchikey` | All parsed rows |
| NORMAN SusDat | `Name` | `CAS_RN_Dashboard` | `SMILES` | `MS_Ready_StdInChIKey` | Reported key required |

The PlastChem reference mapping intentionally has no canonical-SMILES fallback;
this differs from its candidate-inventory mapping and preserves the historical
lookup policy. The NORMAN MS-ready key is a lookup label, not proof that the
associated source SMILES has the same full identity. Reference missing tokens
are interpreted before trimming, matching the historical reference readers.

The versioned `identity-migration-v1` policy applies this precedence:

1. Parse reported SMILES when non-empty and free of `.` and `*` (tier A).
2. If unavailable or invalid, match a syntactically valid full reported InChIKey
   against PubChemLite (B), PlastChem (C), then NORMAN (C). The first row for each
   reference key is retained, including when its structure is unusable; the next
   reference database is then tried. Duplicate rows are exposed in the audit.
3. Otherwise use CAS only when all parseable strict-SMILES candidates from
   PlastChem and NORMAN have one identical full derived key (D). Prefer PlastChem,
   then lexical SMILES and name order, retaining source order for exact ties.
   Reject a CAS hit if a valid reported full key disagrees. CAS checksum
   validation is used in the mapping audit, not retroactively added to this
   historical lookup rule. No names or partial keys are used as matching keys.
4. Retain the record as unresolved (E) if no structure is selected. Records
   excluded by the source-assembly policy remain present and are not resolved.

Route tiers describe precedence, not experimentally calibrated confidence.
Reported structures take precedence even when a supplied key disagrees; those
conflicts remain explicit. Full-key reference lookup may select a multi-component
or wildcard-containing structure even though the reported-SMILES and CAS routes
reject those forms. These inherited decisions require scientific review before
changing the policy; migration validation is not evidence that they are optimal.

RDKit produces canonical non-isomeric and isomeric SMILES, the full InChIKey,
its connectivity block, and a separate key from the non-isomeric representation.
No explicit desalting, tautomer normalisation, charge neutralisation or stereo
collapse is added. The non-isomeric key is retained for later QSAR alignment and
is never the compound aggregation key.

`structure_parse_status`, `identity_key_status` and `aggregation_eligible`
separate parsing from usable identity. A selected parseable structure that
produces no full key retains its route and source evidence but cannot enter
aggregation. Its reported/derived agreement is `derived_key_unavailable`.
This clarifies 90 historical records without changing their group membership.

Aggregation creates one row per valid full derived InChIKey. A representative
is selected by route tier, catalog table order, then original parsed row number.
All eligible source rows remain in `compound_memberships.csv`; repeated source
rows are distinct members. Unresolved and excluded rows remain in
`resolved_records.csv`. CAS and chemical names never define duplicate groups.
The checksum-valid CAS audit records one-to-one relationships, multiple full
identities with shared connectivity, and connectivity conflicts.

The API validates the catalog against assembly, verifies source/reference file
hashes, and records runtime, rule and implementation fingerprints. Reports are
written only after resolution succeeds. Previous outputs can remain after a
failed run; check the matching manifests before using a report collection.

| Stage 2 output | Contents |
| --- | --- |
| `resolved_records.csv` | Every source row, parsed structure, route, statuses, selected reference row and attempted matches |
| `compound_inventory.csv` | Full-key inventory, representative record ID and source-table membership |
| `compound_memberships.csv` | Every eligible record-to-compound link, including repeated source rows |
| `cas_mapping_audit.csv` | Checksum-valid CAS-to-identity relationships and conflicts |
| `reference_lookup_audit.csv` | Duplicate reference keys and ambiguous CAS candidate lists |
| `reference_summary.csv` | Reference inclusion counts and reader warnings |
| `identity_summary.csv` | Counts by source table, route and identity-key status |
| `identity_manifest.json` | Input, runtime, policy, code and output fingerprints |

Selected reference IDs hash source ID, table ID, file SHA-256 and parsed row
number. The reference manifest stores the file, sheet, header and mappings;
`selected_reference_record_number` locates the original parsed row. Input
fingerprints remain the authority for source values and native identifiers.


## Historical regression validation

`plastprior/validation.py` compares generated files with the frozen
`20261006T233429Z` run. `identity_baseline.json` pins its run-manifest fingerprint;
input manifests, both stage checkpoints and the compared artifacts must verify
before comparison proceeds. The old code is never imported or executed, and no
pickle is loaded. Obtain the frozen reference run separately; it is not in Git.

After producing Stage 2 reports, run on macOS or Windows:

```text
python -m plastprior.validation --baseline "path to the frozen run" --results results/stage2 --output-dir results/validation
```

The validator aligns included records by frozen source/table and parsed row
order, verifies each original Name, CAS, SMILES and InChIKey, then saves the row
bridge. For this bridge only, whitespace is trimmed and leading CAS apostrophes
are removed to match the old ingestion output. All original new-project values
remain untouched. It then compares:

- Each record's canonical structures, full/connectivity/QSAR keys, stereo status,
  resolved name, matching route, tier and aggregation eligibility.
- The full compound-key set, each member link with duplicate multiplicity,
  representative identity and fields, and source-table membership.
- All checksum-valid CAS audit relationships, statuses and counts.

Discrete identities, decisions and memberships require exact equality. Summary
counts are diagnostics, not the acceptance criterion. There is no floating-point
tolerance in this stage. Differences or failed prerequisites produce a non-zero
exit status, a failed summary and a reviewable difference report. Baselines are
never rewritten automatically. A notebook execution alone is not a historical
comparison; run this command after reviewing a new implementation.

Two distinctions are explicit rather than hidden in a pass result:

- The 90 parsed records without an identity key use the clarified agreement
  status `derived_key_unavailable`. Their structures, routes and exclusion from
  aggregation must still reproduce the baseline.
- The historical compound CSV includes subsequent QSAR QC. That operation
  reparsed non-isomeric SMILES and changed 10 exported strings. Stage 2 validates
  these against the old **pre-QC record-level representative**, identified from
  the historical member list. The pre-/post-QC differences are exported in
  `stage_boundary_differences.csv`; QC itself is deferred to Stage 3.

Validation also saves `validation_summary.json`, `validation_checks.csv`,
`validation_differences.csv` and `record_alignment.csv`. The report records both
runtimes and the identity-manifest fingerprint. The historical run used an
uncommitted working tree, so its Git commit alone cannot reconstruct that run.
Its code fingerprint and frozen outputs are comparison references, not an
independent certification of chemical correctness. Raw CSV bytes, explanatory
provenance prose and schemas differ by design; later-stage results are outside
this comparison. Native Windows execution remains to be verified separately.


## Stage 3A: frozen QSAR report integration

`integrate_qsar()` in `plastprior/qsar.py` uses the Stage 2 result directly. The
CLI option `--integrate-qsar` runs source inspection, assembly, identity resolution
and Stage 3A in order. Both interfaces use the same functions. No old-project
runtime code, VEGA application, external service, or prebuilt Excel master is
required. The 20 raw report files remain read-only in `data/Vega output`.

`qsar_models.json` declares every model's filename, SHA-256, model/core metadata,
encoding, exact header labels, recognised row widths, prediction fields and
reported units, quality fields, numeric conversions and historical merge fields.
Unrecorded units are labelled explicitly. Undeclared files, changed fingerprints,
unexpected headers or widths, missing rows, repeated/out-of-order row numbers,
and disagreement between model SMILES sequences stop integration. Files are
hashed again after reading and at the end of integration.

**Structure screening and batch identity.** Screening reproduces the historical
100–1000 molecular-weight interval and exclusions for missing/invalid structures,
multi-component structures, absence of carbon and the declared metal list.
Heavy halogenation (at least four halogen atoms) is a warning. The inherited
`charged_structure` flag tests the SMILES text for `+` or `-`; it is not a new
net-charge calculation and is not an exclusion. All compounds and Stage 2 fields
remain present. The reparsed non-isomeric representation is stored separately as
`qsar_smiles`, including the ten previously identified pre-/post-QC differences.

Input order follows the full-key inventory order, keeping the first eligible
representative of each `qsar_inchikey`. The exported input has 10,655 rows from
11,236 eligible full identities. The input text and external four-column row
manifest must reproduce the frozen batch's exact SHA-256 values. These external
column labels (`vega_row_no`, `Qsar_inchikey`, `Inchikey_std`, `Smile_std`) retain
the historical manifest contract. A changed chemical collection cannot reuse
these reports by row without a separately reviewed batch declaration.

**Values and missingness.** `qsar_predictions.csv` retains the 169 historical
model/quality/basic fields as raw text, before numeric conversion or legacy
missing-token projection. Model values are joined many-to-one to the full-key
inventory; 15,125 chemical identities remain distinct. The compound projection
reproduces the 59 retained historical QSAR/basic fields. Ready Biodegradability
is present in the raw model table but was not selected into that historical
compound projection; its predictions are not silently substituted for another
endpoint. No hazard score or common ADI cutoff is applied here.

The Mutagenicity CONSENSUS report supplies Assessment but no ADI. Its ADI is
explicitly listed as absent, never invented as zero. Numeric missing tokens,
conversion failures and true numeric zero remain distinguishable in the raw
values and conversion audit. The legacy Excel reader treated exact `N/A` and
other declared NA tokens as missing. That rule applies only to the compound
projection; `missing_value_audit.csv` records the original non-empty tokens.
For the frozen batch, the `N/A` Assessment projection explains 2,600 compound
cells across the water, soil and sediment persistence models. Raw predictions
retain the literal text.

**Variable-width reports.** BCF Arnot–Gobas, Mutagenicity CONSENSUS and Vapour
Pressure contain rows whose width differs from their header or expanded layout.
The migration retains historical left-aligned padding and extra fields before
Remarks so selected values remain reproducible. It does not infer undocumented
column meanings. Every such row retains file hash, physical line, row number and
all original cells in `report_layout_audit.csv`. This also preserves short-row
text that the legacy layout placed outside the final Remarks column.

**Identity exceptions and source provenance.** The report SMILES sequence is
identical across all 20 frozen reports. RDKit 2026.3.1 finds 15 input positions
whose report structure does not reproduce the input key:

- Fourteen yield different molecular formulae (hydrogen counts in this batch)
  and radical-electron counts. These are observed representation differences,
  not proof of which processing step introduced them or which representation is
  chemically correct. Boron-cluster and radical representations require care.
- Row 4389 cannot be sanitised because of a Kekulization failure. The original
  input structure and the report representation are both retained, together
  with the parser diagnostic. No structure repair is attempted.

The frozen review rows are 938, 951, 3921, 4389, 4396, 5200, 5211, 6542, 7158,
8420, 8448, 9214, 9536, 9695 and 9702. Their declaration permits historical import
for audit, not scientific acceptance. An additional or changed exception stops
integration; there is no percentage-based allowance for new mismatches.

All 15 affected full identities retain their historical prediction values but
have `qsar_identity_verified=False` and `qsar_identity_status=review_required`.
Downstream code must not treat these values as identity-verified evidence.
An exact report/input key match establishes representation agreement only; it
does not establish model reliability or applicability-domain suitability.
Unassociated compounds use `no_report_association`, separately from review cases.

The exceptions link to 58 original inventory records and 300 model-report rows.
Source records retain their frozen-file fingerprints, native IDs, selected
reference identifiers, raw reported values and resolution routes. Report records
retain model/file hashes, physical line numbers and parsed source fields. The
shared row/key links connect these tables without duplicating each source record
20 times. The cause assessment remains pending scientific review: archived text
alone cannot establish whether VEGA processing or report export introduced the
representation change. Resolving it may require the original model execution
records or a separately authorised rerun; Stage 3A does neither.

Outputs are generated under `results/stage3/` and remain ignored by Git:

| Output | Purpose |
| --- | --- |
| `qsar_screening.csv` | Eligibility, molecular weight, warnings, exclusion reasons and separate QSAR SMILES |
| `vega_input_smiles.txt`, `vega_input_row_manifest.csv` | Exact frozen input batch and row-to-identity contract |
| `qsar_predictions.csv` | Raw selected predictions and quality fields for all models |
| `compound_qsar.csv` | Full chemical inventory, historical value projection and identity-review flags |
| `qsar_identity_audit.csv`, `identity_anomalies.csv` | All row identities and a compact exception-only view |
| `identity_anomaly_sources.csv` | Every original source member of affected compounds |
| `identity_anomaly_reports.csv` | Every affected model-report row and its provenance |
| `qsar_model_summary.csv` | Versions, coverage, errors, ADI availability and layout counts |
| `report_layout_audit.csv` | Nonstandard row widths with all raw source cells |
| `numeric_conversion_audit.csv`, `missing_value_audit.csv` | Original missing tokens and explicit conversion outcomes |
| `qsar_manifest.json` | Upstream, report, policy, implementation, runtime and output fingerprints |

**Stage 3A regression.** Use the same frozen run as for Stage 2:

```text
python -m plastprior.validation --stage qsar --baseline "path to the frozen run" --results results/stage3 --output-dir results/validation_stage3
```

The validator first reruns Stage 2 regression (using the sibling `stage2` folder;
`--upstream-results` can specify another location). It then verifies the old
Stage 3 checkpoint/artifacts, all current outputs and upstream/report hashes.
It compares every screening outcome/reason and molecular weight, input row and
SMILES byte sequence, all 169 raw master fields, all 59 projected fields for
every full identity, and unchanged Stage 2 identity fields. It also checks
exception propagation, model-level counts and completeness of the 58 source
and 300 report provenance links.

Text, classifications and missing positions require exact equality. Converted
numbers use exact decimal-value equality, so `1.20` and `1.2` are equivalent but
a nonzero numerical difference fails; no floating-point tolerance is used in
Stage 3A. Excel workbook formatting and metadata are outside the comparison.
The report explicitly excludes every `LRTP_*` field and rejects a Stage 3A output
that contains them. No claim of complete historical Stage 3 reproduction is
made by the Stage 3A validator; the separate Stage 3B validator covers that component.

`qsar_validation_summary.json` records historical agreement and scientific
identity-review status separately. The accompanying checks and per-field
differences remain reviewable. A failed prerequisite or unexplained difference
returns a non-zero exit code; baselines are never updated automatically.


## Stage 3B: Pov/LRTP calculation and identity isolation

`plastprior/lrtp.py` reads the fingerprinted Stage 3A reports, applies the
historical three-compartment fugacity calculation, and writes separate
historical and analysis tables. It imports no legacy repository code at runtime,
does not rerun VEGA, and does not calculate downstream mobility or priority
scores. `--calculate-lrtp` runs Stages 1, 2, 3A and 3B in order; the notebook uses
the same entrypoints. The Stage 3A artifacts remain unchanged.

The numerical kernel was migrated from
`Algorithm/step12b_oecd_lrtp.py` in ChemicalPrio. The source SHA-256 and frozen
run are recorded in `lrtp_parameters.json`, together with the input mapping,
report versions/hashes, units, conversion rules, numerical boundaries and
reference lines. Environmental geometry, transfer coefficients and arithmetic
operation order remain explicit in the kernel and are covered by its source
fingerprint and full historical regression. The historical source describes an
OECD-tool implementation but does not identify a validated official workbook
release. Agreement with the archived Python outputs must not be presented as
independent validation against the official OECD workbook.

| Property | Frozen model field and conversion |
| --- | --- |
| logKow | Meylan-Kowwin predicted LogP; no conversion |
| Air half-life | IRFMN-CORAL prediction in hours |
| Water half-life | IRFMN quantitative persistence prediction in days, multiplied by 24 |
| Soil half-life | IRFMN quantitative persistence prediction in days, multiplied by 24 |
| Vapour pressure | CONCERT/Kode prediction in log10(atm) |
| Water solubility | IRFMN prediction in negative log10(mol/L), not the mg/L column |

The historical conversion is
`logKaw = logVP_atm + pWS_mol_L + log10(101325 / (1000 * R * T))`,
with `R = 8.314` and `T = 298.15 K`. The kernel preserves air, water and soil
emission scenarios, their individual outputs, and the historical aggregation:
maximum scenario Pov, maximum air/water characteristic travel distance, and
maximum scenario transfer efficiency. Numerical outputs are Pov (days), CTD
(km), TE (percent) and PhiAir (dimensionless).

Historical reference lines are Pov = 194.662 days, CTD = 5096.73 km and
TE = 2.2476 percent. Exceedance requires strictly greater values; equality is
not exceedance. These are frozen screening reference lines, not declarations
of regulatory status. Missing/non-finite properties, nonpositive half-lives,
fatal partition-coefficient ranges and solver failures remain distinct audit
conditions. Source Assessment and ADI values are retained; no new ADI cutoff,
quality weighting, missing-value imputation or scientific-rule change is
introduced during this migration.

**Separate calculation and identity status.** A historical `ok` or `warning`
means that the numerical input checks permit calculation. It does not establish
chemical identity, adequate applicability-domain coverage, or scientific
reliability. Stage 3B therefore maintains three separate fields:

- `calculation_status`: the original numerical outcome, including `ok`,
  `warning`, `missing`, `invalid` or `calculation_error`.
- `qsar_identity_status`: the unchanged Stage 3A structure-association status.
- `lrtp_available`: true only for a verified identity with calculation status
  `ok` or `warning`. Quality limitations must still be assessed downstream.

**Identity isolation.** All 15 review-required compounds retain their historical
values and scenario evidence in `lrtp_historical_results.csv`, explicitly marked
`result_role=historical_reproduction_only`, with identity diagnostics. The
analysis table `compound_lrtp.csv` preserves every upstream compound and QSAR
field, but withholds all 12 LRTP numeric/Boolean fields for unavailable records.
For the 15 identity exceptions, `LRTP_input_status` and `lrtp_exclusion_reason`
are `identity_review_required`; `calculation_status` still records the original
`ok`. Empty indicators are never replaced with zero or False. Historical nested
`LRTP_evidence` is omitted entirely from the analysis table to prevent scenario
results from bypassing this exclusion. Full evidence remains in the explicitly
historical table.

The frozen baseline contains 15,125 full identities: 9,305 `ok`, 1,645 `warning`,
3,895 `missing` and 280 `invalid`. All 15 identity exceptions were numerically
`ok`; isolation reduces available results from 10,950 to 10,935. The historical
reference-line counts are 1,415 Pov, 16 CTD and 1,193 TE exceedances. With identity
isolation they become 1,412, 16 and 1,192 respectively; the exclusions are three
Pov cases (input rows 4389, 6542 and 9702) and one TE case (row 9695). These are
explicit policy differences, not failures of historical numerical reproduction.
Neither the representations nor their original predictions are repaired.

Outputs are written under the ignored `results/stage3/lrtp/` directory:

| Output | Purpose |
| --- | --- |
| `lrtp_historical_results.csv` | All original LRTP fields, full scenario evidence and identity diagnostics; historical audit only |
| `compound_lrtp.csv` | Full upstream inventory plus LRTP values subject to identity isolation; no downstream scores |
| `lrtp_input_audit.csv` | Six raw properties, five converted inputs including invalid/missing cases, source quality, calculation and identity status |
| `identity_isolation_audit.csv` | 180 field-level exclusions: 12 fields for each of the 15 review identities, with original values and reasons |
| `identity_anomaly_sources.csv` | All 58 original source records and added LRTP exclusion/identity reasons |
| `identity_anomaly_reports.csv` | All 300 report links with original fingerprints/locations and added exclusion/identity reasons |
| `lrtp_manifest.json` | Upstream, parameter, implementation and output hashes, runtime, scope and counts |

**Validation.** Use the fingerprinted reference run:

```text
python -m plastprior.validation --stage lrtp --baseline "path to the frozen run" --results results/stage3/lrtp --output-dir results/validation_stage3b
```

The validator first runs Stage 3A and Stage 2 regression. It then compares every
historical LRTP field for all 15,125 full keys against the frozen result table,
merged inventory and input audit. Evidence JSON is compared recursively,
including conversion constants, source quality, input values, warnings,
reference lines and every emission scenario. Object key order is ignored;
list order, scalar types, missing locations and exact decimal values are checked.
No floating-point tolerance is used. Changed classifications or unexplained
numerical differences fail validation rather than updating the baseline.

Analysis isolation is validated separately: all upstream fields must remain
unchanged, all withheld fields must be empty, every exclusion reason must match,
all 180 field-level audit entries must be complete, and all 58 source records
and 300 report links must retain their original contents. A successful report
means both historical reproduction and the intentional isolation policy passed;
it does not mean the analysis projection is identical to the old unfiltered
results. The validator reports independent official-tool validation and scientific
identity review as outstanding.

Tests include a frozen numerical example, unit/sign conversion, missing versus
zero/False, non-finite and nonpositive inputs, warning/fatal boundaries, strict
reference-line comparisons, pivoting/singular systems, solver failures,
provenance preservation, fingerprint failures and identity-isolation safeguards.
Run the CLI and notebook independently and compare their generated file hashes
when verifying a release. Native Windows execution remains a separate required
check before claiming cross-platform validation.


## Stage 4A: basic source evidence

`plastprior/evidence.py` assembles basic observations from the 11 inventory
tables and attaches source provenance. The field maps, source order, matching
aliases and frozen reader policy are declared in `evidence_fields.json`.
`_evidence_rules.py` contains the migrated selection rules and classification
summaries, separated from file I/O. The original implementation fingerprints
are recorded; no code is imported from the old repository at runtime.

`--integrate-evidence` runs Stages 1, 2, 3A, 3B and 4A. The notebook calls the
same functions. No specialist LitChemPlast/FCChumon resolver, analytical
detectability annotation, GIC integration, or downstream score is executed.
Source-native scores such as PlastChem Hazard_score remain observations with
source links; they are neither recalculated nor treated as PlastPrior scores.

**Selection rules.** Each Stage 2 member queries its original source using
InChIKey, then CAS, then SMILES. Comparisons use trimmed, case-insensitive exact
text. The first matching parsed row is selected; all alternative hits are
retained with `not_selected_first_row_policy`. The historical identity gate
compares InChIKey/CAS matches against a source-priority identity seed. SMILES
matches are accepted by the historical rule but explicitly labelled as text
matches rather than identity proof. Unknown or mismatched identities are
excluded with the original reason. This secondary evidence-selection identity
must not overwrite the canonical full InChIKey established in Stage 2.

Identity attributes use the first valid value in the declared source and
column order. Other mapped observations retain distinct values per source,
while the field audit preserves every observation, including duplicates.
PlastChem polymer context and concern annotations use the last valid row;
nonpositive concern-list annotations do not erase a previously positive entry.
The additional classification audit records selected, superseded, missing,
invalid and excluded values. The historical rule omits a classification block
when all its final values are zero; these observations are retained in the audit
with `omitted_all_zero_block_historical_rule`. This omission must not be
interpreted as absence of source observations. These rules preserve historical behaviour for
review and are not claims that source precedence establishes scientific quality.

Stage 4A intentionally retains historical pandas type inference and default
missing-token handling. This differs from Stage 2's preservation of textual
reported identifiers. `evidence_source_rows.jsonl` therefore contains the full
**reader-interpreted** row, plus original source hash, sheet, parsed/physical row
positions, native identifier and Stage 2 `reported_fields_json`. Original file
bytes remain unchanged. Inferred values are not a replacement for the source
files. Field mappings report unavailable columns rather than inventing aliases
that would silently change the frozen evidence selection.

**Prediction isolation.** All 15 identity-review compounds remain in the
inventory with their independent database observations. The analysis table
withholds all 57 projected QSAR model fields for them and retains all 12 existing
Pov/LRTP exclusions. `prediction_isolation_audit.csv` records 1,035 field entries,
original upstream values, actions and identity reasons. Empty flags are never
replaced with False or zero. `qsar_evidence_available` reflects the upstream
identity check only; model applicability and evidence quality still require
assessment. Historical QSAR/Pov/LRTP values, 58 source-record links and 300
model-report links remain in the fingerprinted Stage 3 reports, referenced by
the Stage 4A manifest. This stage does not resolve the scientific identity issue.

Outputs under the ignored `results/stage4/` directory are:

| Output | Purpose |
| --- | --- |
| `compound_evidence.csv` | Analysis inventory, seven basic evidence fields and prediction isolation |
| `basic_evidence_historical.csv` | Full keys and seven historical basic fields; no model predictions |
| `evidence_field_mapping.csv`, `evidence_match_mapping.csv` | Declared source fields, availability, lookup columns and selection rules |
| `evidence_source_summary.csv` | Source fingerprints, reader policy, row counts and warnings |
| `evidence_match_attempts.jsonl` | Every member query, search attempts, first selected row and identity-gate outcome |
| `evidence_candidates.jsonl` | Every matched row, including unselected alternatives |
| `evidence_source_rows.jsonl` | Complete reader-interpreted source rows and original provenance |
| `basic_evidence_audit.jsonl` | Historical field observations/mismatches plus source and query links |
| `classification_selection_audit.jsonl` | Last-valid-row selection, supersession and exclusion decisions |
| `prediction_isolation_audit.csv` | Each withheld QSAR field and existing Pov/LRTP exclusion |
| `evidence_manifest.json` | Upstream, input, mapping, implementation and output hashes, runtime and counts |

**Field-level validation.** Run:

```text
python -m plastprior.validation --stage evidence --baseline "path to the frozen run" --results results/stage4 --output-dir results/validation_stage4a
```

The validator reruns the Stage 2/3A/3B comparisons and verifies frozen Stage 4
checkpoint/artifact hashes. The archived final Stage 4 includes later enrichment,
so it cannot be used unmodified as the 4A baseline. The validator removes only
its three specialist JSON blocks and restores the generic LitChemPlast count
from the frozen **basic** field audit; it does not regenerate a baseline using
the new extraction code. GIC and analytical columns are outside this comparison.

Every basic JSON value is compared recursively for all 15,125 full identities,
including missing positions, scalar types and list order. Five classification
summary fields require exact text equality. All 363,601 historical field events,
including 1,493 identity mismatches, are compared with duplicate multiplicity.
Numeric values require exact decimal equality without tolerance. Canonical
identities and all unaffected upstream columns must remain unchanged. The
validator separately checks the 1,035 intended prediction exclusions, membership
coverage, source links, candidate counts and classification selections. A
successful result means historical agreement **at the 4A boundary** and correct
isolation, not equivalence to the full later-stage result or independent proof
of scientific correctness. Unexplained differences fail validation.

Tests cover precedence, identity exclusions, duplicate observations,
classification overwrite/list rules, changed source hashes, missing versus
zero/False, prediction isolation and the pre-enrichment baseline boundary.


## Stage 4B: literature associations and human detection

`plastprior/evidence_specialists.py` integrates LitChemPlast and FCChumon after
Stage 4A. `evidence_specialists.json` declares source tables, required fields,
detection definitions, count policies and the original implementation hashes.
Both resolvers and their provenance handling reside in this one module. No
legacy repository code is imported at runtime. `--integrate-specialists` runs
Stages 1 through 4B; `--integrate-evidence` still stops at 4A.

**Identity association.** The representative CAS is insufficient for specialist
matching. `cas_identity_view.csv` reconstructs all checksum-valid CAS aliases
from Stage 2 member records, using the existing CAS mapping audit. The compound
status is the most severe alias status: one-to-one, multiple full keys with one
connectivity block, or conflicting connectivity blocks. Missing valid aliases
remain `invalid_or_missing`. `cas_source_links.csv` retains every member and its
reported CAS, including members without a valid CAS. This is an evidence view;
no identity is resolved again and no compound is merged.

**LitChemPlast.** The Chemical sheet supplies `Chem_id`, `INCHIKEY`, `CASRN` and
`count_LitChem_id`. The LiteratureChemical sheet supplies `Chem_id`, `LitChem_id`
and `Lit_id`. An exact full InChIKey match has precedence. CAS fallback considers
only Chemical rows with a missing or invalid full key, and requires a one-to-one
target mapping and exactly one CAS candidate. A valid conflicting source key
cannot be bypassed by CAS. Candidates excluded by precedence, identity conflict
or ambiguity retain their source and relationship row identifiers.

Counts use unique `LitChem_id` relationships and unique `Lit_id` publications,
reported separately. Duplicate associations are retained but not counted twice.
Multiple Chemical rows with the same key are aggregated before counting. The
source-declared maximum is retained for comparison; it is not added to the
relationship count. The public integration entrypoint requires the frozen
relationship sheet and does not silently fall back to declared counts if it is
missing. A matched chemical with zero relationships remains a selected source.
The specialist count replaces the generic count only in the new 4B output;
Stage 4A artifacts remain intact.

**FCChumon.** S1 uses `FCChumon entries (detection "YES")`; S2 uses
`Studies reporting: "FCC detected YES"` for detection and separately retains
`FCChumon entries (detection "YES")` as the database-entry count. Counts take
the maximum within each sheet/CAS group. They are not summed across duplicate
rows or sheets. Selection requires an unambiguous target CAS and exactly one
sheet/CAS candidate; multiple aliases or cross-sheet candidates are rejected.
Candidate audits identify the rows supporting each maximum and lower-count
rows that were not selected for that maximum.

The analysis fields distinguish `detected`, `matched_without_positive_count`,
`no_match`, and rejected associations. `fcchumon_detected` is empty when evidence
is unavailable. Historical resolution JSON retains the original zero/False
conventions with explicit matching status; these values must not be interpreted
as observed absence when the association was not selected. A missing or
non-numeric source count was historically converted to zero, and FCChumon
fractional counts were truncated to integers. The conversion audit retains the
raw value and reason. Negative counts fail integration. Historical coercion is
not an independent endorsement of source completeness or measurement quality.

**Membership and availability.** Stage 2 `source_tables_json` is unchanged.
`litchemplast_evidence_available` is a separate evidence-association annotation.
The historical projection retains `db_LitChemPlast` for comparison: the old
resolver marked 36 additional compounds as members after successful specialist
matching. That compatibility column is omitted from the analysis table so it
cannot overwrite original source membership. Specialist availability establishes
only that the declared matching rule selected evidence, not scientific certainty.

**Identity-review compounds.** All 15 QSAR representation exceptions retain
empty values in the 57 QSAR and 12 Pov/LRTP fields. Identity reasons and upstream
availability flags are unchanged. Independently matched source evidence uses
the canonical Stage 2 identity and its guarded CAS aliases. In the frozen run,
two exceptions have full-key LitChemPlast matches with four and one associated
records respectively, each from one publication; none of the 15 has a FCChumon
match. These are regression outcomes, not hardcoded overrides. The dedicated
review table exposes all 15 outcomes and exclusion reasons. The original QSAR
report links and historical model values remain in Stage 3, with provenance
linked through the unchanged upstream manifests.

Outputs are written under the ignored `results/stage4/4b/` directory:

| Output | Purpose |
| --- | --- |
| `compound_specialist_evidence.csv` | Analysis inventory with specialist evidence and inherited model exclusions |
| `specialist_historical.csv` | Full keys, 4B evidence JSON and the legacy LitChemPlast membership projection |
| `cas_identity_view.csv`, `cas_source_links.csv` | All compound CAS aliases, ambiguity details and member-level source links |
| `litchemplast_resolution_audit.jsonl`, `fcchumon_resolution_audit.jsonl` | One complete historical resolution record per compound and source |
| `specialist_source_rows.jsonl` | All four reader-interpreted source tables, file hashes, worksheet/row positions and native IDs |
| `specialist_candidates.jsonl` | Selected and rejected candidate groups, linked source rows and maximum-count contributions |
| `literature_link_decisions.jsonl` | Each selected relationship row, Chemical row links and unique/duplicate counting decisions |
| `count_conversion_audit.jsonl` | Original count values, conversions and historical aggregation policy |
| `identity_review_evidence.csv` | All 15 model-identity exceptions and their independent source-evidence outcomes |
| `specialist_manifest.json` | Scope, policy/code/input/upstream/output fingerprints, source warnings, runtime and counts |

Source-row identifiers reuse Stage 2 identifiers for Chemical and FCChumon rows.
Relationship-row identifiers use the same source ID, table ID, file hash and
parsed-row-number scheme. Original workbooks remain unchanged. The ledger
contains reader-interpreted values under the historical pandas policy, not
byte-for-byte worksheet cell encodings. Orphan or missing Chemical references
are retained and labelled rather than silently removed from the source ledger.

**Validation.** Run:

```text
python -m plastprior.validation --stage specialists --baseline "path to the frozen run" --results results/stage4/4b --output-dir results/validation_stage4b
```

The validator first runs the complete Stage 4A regression and its upstream
checks. It compares all 15,125 compound CAS views and both 15,125-row specialist
audits against the frozen artifacts, field by field. Complete evidence JSON is
compared with the archived final Stage 4 after removing only the Stage 4C
analytical-detectability block; GIC top-level columns are excluded. The 4B
literature counts are retained in this comparison. Object key order is ignored;
list order, scalar types, missing positions and exact decimal values are checked
without numerical tolerance. The legacy membership projection is also compared.

Independent checks cover source provenance, candidate selection, relationship
contributions, review-subset completeness, all 1,035 prediction-field exclusions,
and unchanged upstream fields apart from the explicitly enriched evidence JSON.
Historical agreement is separate from independent scientific identity review.
Expected frozen outcomes are 3,164 exact-key and 80 fallback LitChemPlast matches,
6 LitChemPlast ambiguity rejections, 388 FCChumon matches including 229 positive
counts, and 23 FCChumon ambiguity rejections. Counts alone do not establish
agreement; unexplained field differences fail validation.

Tests exercise source-key conflicts, CAS ambiguity, cross-sheet rejection,
duplicate association counts, zero relationships, different S1/S2 definitions,
maximum selection, numerical coercion, source hash failures and model-isolation
safeguards. CLI/notebook output equality and unchanged earlier-stage hashes are
checked separately. Native Windows execution remains a separate verification
requirement. The 4B entrypoint stops before 4C; the annotation entrypoint below
adds 4C separately. All downstream scoring remains outside this implementation.


## Stage 4C: analytical-platform predictions and regulatory-list associations

`plastprior/evidence_annotations.py` adds annotations to the Stage 4B analysis
view. `evidence_annotations.json` declares the exact input files and hashes,
NORMAN field mappings and selection order, GIC bridge mappings, tag classes,
repository revision and provenance limitations. No legacy repository is needed
at runtime. Earlier outputs are read without modification.

```text
python main.py --integrate-annotations
python -m plastprior.validation --stage annotations --baseline "path to the frozen run" --results results/stage4/4c --output-dir results/validation_stage4c
```

The command executes Stages 1 through 4C. The existing `--integrate-specialists`
command still stops at 4B. All processing uses the frozen local sources; no
inventory download, metadata generation, identity repair or scoring is performed.
Missing or changed input files fail explicitly.

### NORMAN selection and interpretation

The canonical full key is compared to `MS_Ready_StdInChIKey` after trimming and
uppercasing. For duplicate keys, the historical ranking first maximises the
number of populated analytical fields, then the maximum RPLC/GC/ESI/EI
probability, and retains the first source row for remaining ties. Probability
coercion precedes ranking; zero is a valid value, while nonnumeric values become
missing with an explicit conversion reason. Every source candidate, rejected
candidate, raw interpreted field and physical worksheet row is retained. CSV
bridge records use parsed record numbers; physical CSV line numbers are not
asserted because quoted multiline cells and blank lines can change them.

The 16 analytical fields and three source identity fields have explicit output
mappings. Predictions describe platform amenability, not measured occurrence or
experimental detection. The historical `derived_scores.lc_esi` and `gc_ei` values
are pairwise probability minima retained only as annotation metadata. They are
not exposure, hazard or priority scores. Missing predictions do not establish
analytical inaccessibility.

### GIC matching and review boundaries

The frozen rule tries an available full InChIKey, then the union of CIDs from
PubChemLite `Related_CIDs` and SusDat `PubChem_CID`, then `name_resolved`. SusDat
uses both its standard and MS-ready keys. The inventory has no InChIKey field;
actual matches therefore use CID or name. A non-auxiliary listing takes
precedence; an auxiliary-only candidate is retained only if no such listing is
found. All attempted paths and their selection or exclusion reasons are saved.

Names use the pinned GIC identifier lookup without added fuzzy matching. Every
selected name association has `gic_name_review_required=True`. CID multiplicity
and SID multiplicity have separate flags. Neither name nor CID matching is
proof of chemical identity. The pinned GIC library builds a **global identifier-to-tag
index**: the same identifier string can collect tags from multiple SIDs. A SID
query then unions the tags of all its identifiers. Shared names, including
placeholder-like names, can therefore introduce tags that do not occur in the
matched SID's own JSONL record. Historical results are preserved, with
`gic_shared_identifier_tag_expansion=True` where the selected association adds
such tags. This is an additional review requirement, not identity confirmation.
The trace retains local versus effective tags, added tags for each query, and
all contributing identifier occurrences, including other SIDs and physical
JSONL line numbers. No automatic correction or scoring is applied.

The seven historical GIC columns are reproduced, including the distinction
between `available` with no match and `not_queried` with an unavailable inventory
count. Regulatory classes are fixed historical annotations, not a conclusion
about current legal status, jurisdictional applicability or exposure.

### Metadata and dependency provenance

The inventory, PubChemLite and SusDat hashes are compared with the frozen run's
input manifest. The metadata CSV was not hash-recorded in that manifest. Its
current bytes are pinned, and all effective fields for tags used in the historical
GIC audit are compared individually. Unused tags have no such historical audit
coverage. `source_date` values are preserved as reported, not independently
verified retrieval or effective dates. The missing historical file hash remains
an explicit limitation even when all used fields agree.

The dependency is the Global Inventory Compiler at the repository commit in
`requirements.txt`; **the PyPI package named `gic` is unrelated**. Installation
requires Git and access to that repository. For offline installation, build a
wheel from the declared revision and install it with its dependencies; do not substitute the same-named PyPI package. The
runtime verifies version and the complete Python source fingerprint (normalised
to LF); recorded VCS origins must also match. Missing VCS origin metadata is
reported explicitly for wheel installations. The pinned
implementation matches the current legacy environment, but the old run did not
record a GIC package version, so historical version identity is not claimed.

### Identity isolation and outputs

The 15 upstream identity reviews and 58 compound-to-source links are retained.
All 57 QSAR and 12 Pov/LRTP values remain blank in the analysis table, and both
availability flags remain false. Existing Stage 3 historical files are retained
unchanged. Independent NORMAN/GIC annotations use the canonical Stage 2 key and
do not resolve the VEGA representation discrepancies.

Outputs are local under `results/stage4/4c/` and ignored by Git:

| Output | Purpose |
| --- | --- |
| `compound_annotated_evidence.csv` | Complete analysis view with inherited model isolation and association review flags |
| `annotation_historical.csv` | Full-key projection of the complete evidence JSON and eight historical annotation columns |
| `norman_candidates.jsonl`, `norman_resolution_audit.jsonl` | All ranked source candidates, conversions, decisions and per-compound selected source IDs |
| `cid_bridge_source_rows.jsonl`, `cid_bridge_links.jsonl` | Target-relevant source rows and eligible key/CID edges, including missing CID reasons |
| `gic_resolution_audit.jsonl`, `gic_match_decisions.jsonl` | Historical query audit plus source-linked selection/exclusion decisions |
| `gic_source_rows.jsonl`, `gic_identifier_tag_sources.jsonl` | Queried SID rows, local/effective tags and all shared-identifier tag contributors |
| `gic_metadata_audit.jsonl` | Raw metadata rows, effective values and historical provenance limits |
| `identity_review_annotations.csv`, `identity_review_source_links.jsonl` | Unresolved model exceptions and original member links |
| `annotation_manifest.json` | Input, upstream, implementation, policy, dependency and output fingerprints |

The validator first reruns all upstream comparisons. It then checks all eight
historical annotation fields, the complete evidence JSON and every scientific
GIC audit field. Only historical absolute input paths and `generated_at` are
separated into `runtime_provenance_comparison.jsonl`: the new manifest records
portable input parts and hashes and deterministic outputs omit timestamps.
Comparison retains JSON list order, scalar types, missing positions and exact
decimal values without numerical tolerance. It also checks unchanged upstream
columns, review flags, source links, SID-to-tag provenance and all 1,035 isolated
prediction cells. Equal row counts alone do not establish agreement.

The frozen reference contains 6,294 NORMAN matches and 9,620 GIC associations
(8,488 CID bridges and 1,132 name matches). Among the 15 unresolved identities,
three have NORMAN predictions; six have GIC CID matches, two name matches and
seven no match. These are regression expectations, not eligibility overrides.

The frozen trace identifies one additional GIC review case:
`GUUHFMWKWLOQMM-NTCAYCPXSA-N` (`alpha-Hexylcinnamaldehyde`). Its CID bridge reaches
SID 268665, which contains the shared name `<CAS RN deleted>`. Other inventory
rows with that name contribute `JP-CSCL_CI` and `JP-CSCL_CII` through the global
identifier index. The historical `prohibited_or_phaseout` label is retained for
reproduction and explicitly flagged; it must not be interpreted as an
independently confirmed classification. This association review is separate
from the 15 VEGA identity reviews and is not automatically corrected here.


## Persistence and mobility assessment (Stage 5A)

`plastprior/hazard.py` evaluates P and M only. `hazard_policy.json` declares the
input columns, units, decision thresholds, source precedence and fingerprints of
the historical implementations examined during migration. Runtime execution does
not import the old project or read its Stage 5 scores. The historical results are
recomputed from this project's verified Stage 3 historical predictions and Stage
4C evidence. The validator alone reads the frozen Stage 5 outputs as a reference.

Run the complete workflow through Stage 5A:

```text
python main.py --assess-pm
```

The P/M rules preserve the historical screening conventions:

- P: IRFMN water, soil and sediment assessments map `nP`, `nP/P`, `P/vP`, `vP`
  to 0, 0.5, 1 and 2. ADI must be present and at least 0.5. Use the maximum;
  ties select the first compartment in water, soil, sediment order.
- Aquatic M: OPERA log10 Koc in L/kg, with ADI at least 0.5; values below 2,
  below 3, below 4 and at least 4 map to 2, 1, 0.5 and 0, respectively.
- LRTP M: both CTD (km) and TE (percent, not fraction) must be available, with
  status `ok` or `warning`. Use `max(CTD / 5096.73, TE / 2.2476)`; ratios at
  least 1, 0.5 and 0.25 map to 2, 1 and 0.5, respectively, otherwise 0.
  This inclusive scoring boundary is distinct from the strict exceedance flags
  retained in Stage 3B.
- M: maximum usable aquatic/LRTP score; retain both bases on ties. For either
  P or M, usable independent evidence, including zero, precedes curated fallback.
  Curated selection uses PlastChem first, then alphabetical database order,
  retaining the first numeric value (or a recognised P label if no numeric value
  is available). Historical curated values such as 0.25 remain unchanged.

These are inherited screening rules, not a newly validated regulatory
classification. Historical agreement establishes migration fidelity, not model
accuracy or scientific validation of the thresholds.

`compound_pm_hazard.csv` is the eligible analysis table. All Stage 4C columns,
including GIC review flags, are preserved. `pm_historical.csv` has an explicit
`historical_reproduction_only` role and must not feed subsequent analysis.
Analysis checks availability and rejects model inputs leaked into the 15
identity-review rows. Those compounds may still use independently supported
curated P/M evidence; no such fallback exists in the current cohort. Consequently,
9 previously available P values and 15 M values become unavailable, not zero.
Aquatic and LRTP subscore availability decreases by 10 and 15, respectively.
The other 15,110 compounds must retain all eight P/M fields exactly.

GIC name matches (1,132 compounds) and the shared-identifier tag expansion
(one compound) remain flagged and unresolved. Neither GIC fields nor NORMAN
analytical-platform predictions are in the scoring input allowlist. The validator
perturbs these annotations for every compound and checks that P/M results and
evidence remain unchanged.

Outputs under `results/stage5/` include:

| File | Purpose |
| --- | --- |
| `compound_pm_hazard.csv` | Stage 4C evidence plus isolated P/M analysis and availability reasons |
| `pm_historical.csv` | Recomputed historical P/M values, bases and evidence; comparison only |
| `pm_summary.csv` | Availability, missingness and zero counts for both views |
| `identity_review_pm_impacts.csv` | Eight before/after fields for each of the 15 compounds, with reasons |
| `persistence_*_audit.jsonl`, `mobility_*_audit.jsonl` | Separate historical and analysis evidence audits |
| `pm_curated_source_links.jsonl` | Stage 4A P/M observations, original source IDs and selection/exclusion reasons |
| `pm_decisions.jsonl` | Compound/dimension selection, availability, VEGA row and upstream manifest links |
| `identity_review_source_links.jsonl` | The 58 original source memberships of the review cohort |
| `hazard_manifest.json` | Policy, implementation, model mapping, input/output hashes and counts |

Validate against the pinned run, supplying its local directory:

```text
python -m plastprior.validation --stage hazard-pm --baseline PATH_TO_FROZEN_RUN --results results/stage5 --output-dir results/validation_stage5a
```

Validation recursively checks Stages 1–4C and verifies the frozen Stage 5
checkpoint/artifacts. It compares all 15,125 historical rows for four numeric
scores, two basis fields and two recursively compared evidence JSON objects,
plus both full audit lists. Numeric values use exact decimal comparison, without
a tolerance; JSON key ordering and numeric spelling are immaterial. Nonreview
analysis rows must match the historical reference; review changes are recorded
separately in 120 field-level impact rows. Hash-verified deterministic replay
checks every Stage 5A artifact, while upstream-field and source-lineage checks
ensure that no records or review flags have been lost. No B/T, exposure or
aggregate priority scoring is added by this stage.


## Bioaccumulation and toxicity assessment (Stage 5B)

`plastprior/hazard_bt.py` extends the Stage 5A analysis with B and T as separate
dimensions. `hazard_bt_policy.json` declares model order, endpoint fields, units,
ADI rules, score cutoffs, structural triggers and source-code fingerprints. It
uses verified local Stage 3 inputs and Stage 4 evidence; it does not import the
old project or read historical Stage 5 scores during calculation. The Stage 5A
implementation and its reports remain unchanged.

Run through Stage 5B with:

```text
python main.py --assess-bt
```

The inherited screening rules are:

- BCF: select the first usable model in Arnot–Gobas, CAESAR, Meylan order, with
  nonmissing prediction and ADI at least 0.5. This is not a maximum across models.
  Predicted log10 BCF (L/kg) at least 3.7, 3.0 and 2.0 maps to 2, 1 and 0.5,
  respectively; values below 2.0 map to zero.
- Structural B: count Cl/Br atoms and those attached to six-member all-carbon
  aromatic rings. At least four total or two ring-bound Cl/Br atoms gives 2;
  otherwise at least two total or one ring-bound gives 1. F and I do not enter
  this rule. An untriggered rule is unavailable, not zero. Parsing failure and
  missing structure retain explicit statuses. RDKit is required; install the
  pinned dependencies before running this pathway.
- Final B: maximum of the selected BCF and structural scores, with BCF first on
  ties and all tied bases retained. A usable independent zero still precedes
  curated evidence.
- T: use Ames consensus, CAESAR/ISS carcinogenicity, CAESAR developmental
  toxicity, IRFMN-CERAPP ER effect and IRFMN fish acute LC50. Positive binary
  endpoints score 2 except ER (1); negative endpoints score zero. Fish LC50 in
  mg/L at most 1, 10 and 100 maps to 2, 1 and 0.5, respectively; higher values
  map to zero. Select the maximum usable endpoint, retaining the first on ties.
  Endpoint-specific negative labels are parsed before generic labels.
- Ames has no ADI field in the historical configuration. Other T endpoints
  require ADI at least 0.5. Every endpoint, including Ames, requires an eligible
  identity association; the absence of an ADI field is not an isolation override.
- Curated B/T: only when independent evidence is unavailable, select PlastChem
  first, then other databases alphabetically, retaining the first numeric value.
  Source values such as 0.25 remain unchanged. Toxicological labels are retained
  in audit context but are not converted into scores.

These rules reproduce historical screening conventions. Their migration does
not independently validate the structural heuristic, cutoff values or endpoint
aggregation. Any scientific rule revision requires separate review and a new
comparison baseline.

**Structural representation.** The structural pathway uses `qsar_smiles` from
local Stage 3 screening of Stage 2 input structures, never `Basic | Smile_std`
from model reports. This representation equals the frozen Stage 5 `Smile_std`
for all 15,125 compounds. Ten input structures have different text after local
standardisation, including removal of explicit hydrogen notation; these are
recorded in `bt_structure_mapping.csv` without overwriting Stage 2 identity
fields. The mapping includes original structure text, selected representation,
source representative ID, upstream manifest hash, structural counts/triggers
and RDKit version. Using this non-isomeric representation follows the historical
Cl/Br pathway; it does not merge full chemical identities.

**Identity isolation.** All 57 QSAR fields and 12 Pov/LRTP values/flags remain
withheld for the 15 unresolved associations. Independent local structures and
curated observations remain eligible. Within this cohort, four former BCF-based
B scores become unavailable, one structural B score remains, and ten B scores
remain unavailable. All 15 QSAR-based T scores are excluded: five are replaced
by PlastChem evidence and ten become unavailable. Of the five replacements,
three increase from zero, one decreases and one retains its numeric value while
changing its basis. Scores, bases and evidence are audited separately, so an
unchanged numeric value does not conceal a source change. Expected availability
is 10,068 historical versus 10,064 analysis B scores, and 12,885 versus 12,875 T
scores. Unavailable results are never assigned zero.

GIC name-match and shared-identifier-expansion flags remain unresolved and are
carried forward verbatim. GIC and NORMAN annotations are outside the B/T input
allowlist. A GIC association issue does not invalidate independent structure,
curated B/T or otherwise eligible QSAR evidence for that compound.

Outputs are written under `results/stage5/5b/`:

| File | Purpose |
| --- | --- |
| `compound_pbmt_hazard.csv` | All Stage 5A fields plus isolated B/T dimension results and availability reasons |
| `bt_historical.csv` | Recomputed historical B/T scores, bases and evidence, for comparison only |
| `bt_summary.csv` | Availability, missingness and zero counts in both views |
| `bt_structure_mapping.csv` | Input-to-scoring structure mapping and structural-rule trace |
| `identity_review_bt_impacts.csv` | Six before/after fields per review compound, with source-change reasons |
| `bioaccumulation_*_audit.jsonl`, `toxicity_*_audit.jsonl` | Full historical and analysis evidence audits |
| `bt_curated_source_links.jsonl` | Stage 4A B/T observations and selection/exclusion provenance |
| `bt_decisions.jsonl` | Model/endpoint/pathway selection, exclusions, unvisited lower-priority models and source links |
| `identity_review_source_links.jsonl` | All 58 original memberships of the review cohort |
| `bt_manifest.json` | Policy, implementation, shared policy dependency, model mapping, upstream/output hashes and runtime |

The PBMT analysis table contains four independent dimensions, not an aggregate
hazard or priority score. `bt_historical.csv` has the role
`historical_reproduction_only` and is not an eligible downstream analysis input.

Validate against the pinned historical run:

```text
python -m plastprior.validation --stage hazard-bt --baseline PATH_TO_FROZEN_RUN --results results/stage5/5b --output-dir results/validation_stage5b
```

Validation recursively checks Stage 5A and all earlier stages, verifies the
frozen Stage 5 checkpoint/artifact hashes, and compares all six B/T fields plus
both complete audit lists by full InChIKey. Numeric comparisons are exact;
JSON comparisons retain nesting, array order and missingness while ignoring
object-key order and numeric spelling. Nonreview analysis rows must reproduce
the historical fields exactly. The 15 review rows are checked against separately
inspected structure/curated expectations, including the three T increases.
All 90 field-level review effects, structure mappings and source ledgers are
verified through deterministic reconstruction. Perturbing GIC/NORMAN annotations,
model-report structures and audit-only toxicological labels must leave B/T
scores, bases and scoring evidence unchanged. Native Windows validation remains
outstanding; code uses the existing cross-platform Python and RDKit dependencies.


## Interpretation and verification

- **Parsed rows** are data rows returned by the declared reader after the
  selected header. pandas omits blank physical lines in CSV inputs and may omit
  trailing empty worksheet rows.
- **Non-empty rows** have at least one cell that is neither missing nor an empty
  or whitespace-only string. This is a table-level diagnostic, not a chemical
  identifier validity check.
- Rows may contain duplicates, unresolvable identifiers, or non-chemical entries.
  Do not sum row counts across sources or interpret them as unique chemicals.
- Stage 1/2 source-native values and column labels are preserved. Literal strings
  such as `NA` are not silently converted into missing values at those stages.
  Stage 4A separately declares its historical reader conversions above. Descriptive output and
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


## Stage 6A: exposure evidence intake and eligibility

```text
python main.py --audit-exposure
```

This runs the preceding stages, then writes evidence and eligibility reports to
`results/stage6/6a/`. It does not compute exposure scores, aggregate PBMT scores,
select a numeric maximum, rank chemicals or run live database queries. The
upstream Stage 5B analysis table remains the authority for PBMT results.
`plastprior/exposure_inputs.json` declares frozen inputs, fingerprints, identity
allowlists, presence states and eligibility rules; `exposure_inputs.py` streams
observation ledgers. The Notebook adds one compact Stage 6A cell.

**Frozen inputs.** The canonical production and market tables are imported
historical derived inputs, not independently rebuilt raw-source transformations.
Under `data/ExposureReference/20261006T233429Z/`, supply these exact files from
the pinned run: `production_volume_evidence.csv`, `market_presence_evidence.csv`,
`source_registry.csv`, the production/market `input_manifest.csv`, the root
`run_manifest.json` and `input_manifest.json`, and the Stage 6 `checkpoint.json`
renamed to `stage6_checkpoint.json`. The four canonical files originate from
`06. ExposureScoring/production_market_evidence/runs/20261006T233958Z-5e6b4a8b/`.
All paths and SHA-256 values are declared in the policy. Original official
source files remain under `data/Official_Production_Volume_Data/`; patent,
PubMed and PubChemLite paths are also policy-defined. All inputs remain ignored
by Git and require separate distribution and licensing review for publication.
Runtime does not import or require the old project.

The pinned run/checkpoint chain verifies all four canonical files. The 32
production-input manifest entries and every raw-file reference are checked
against local bytes. Multiple raw references in a cell are paired in their
recorded order. `source_response_sha256` is retained as a historical response
fingerprint, not falsely checked as a whole-file hash. Raw files are checked
again before the success manifest is published. These checks establish input
consistency, not independent confirmation of the original transformations or
chemical identity assignments.

**Market identity gate.** Every canonical source field and record occurrence
is retained. `source_row_number` denotes the parsed CSV record position including
the header, not a physical line number. An accepted full-key association,
in-scope compound and eligible compound-level source are required before a
qualitative presence state can contribute. Confidential evidence can qualify
without a numeric quantity. Unknown, not found, confirmed zero, confidential,
historical and positive states remain distinct. National-context records remain
in the audit but cannot supply compound-level evidence. The historical
pre-gate presence state and evidence count are retained separately.

Numeric qualification checks bounds and units without selecting or adding
quantities. Annual tonnes and tonnes with an unspecified reporting period
remain distinguishable; unspecified periods are never silently annualised.
Jurisdiction, activity, source scope and non-additivity warnings remain attached
to each record. All 17,735 valid legacy PlastChem observations are retained;
7,968 UCSF observations remain visible with an unsupported-source reason.
The source ledger links back to all Stage 4A exposure observations, including
source selection and exclusion reasons. Specialist source membership,
LitChemPlast association and FCChumon detection are retained as different facts.

**GIC gate.** All 1,132 name-only associations require review and have an empty
eligible inventory count, not zero. A qualifying inventory tag must be supported
locally on at least one matched SID and classified by the frozen metadata as
industrial inventory/registration/use, excluding auxiliary tags. Shared-identifier
expansion flags remain visible. For `GUUHFMWKWLOQMM-NTCAYCPXSA-N`, all 12 industrial
inventory tags have direct support across the matched SIDs. The unsupported
`JP-CSCL_CI` and `JP-CSCL_CII` associations are excluded; they are also outside
the industrial-inventory class. A completed no-match lookup is distinct from
an unqueried record and does not establish absence from real-world use.
Historical metadata acquisition hashes remain unavailable; these are frozen
classifications, not a current regulatory verification.

**Other exposure evidence.** Every PubChemLite, external patent and PubMed
record is retained with raw fields and source fingerprint, including records
outside the compound universe. Patent zero-baseline correction eligibility
requires a completed, consistent query and no existing nonzero curated or
PubChemLite patent evidence. A nonempty query error requires review even if a
terminal status and count are present, because multi-CID retrieval may be
partial. No CID, no candidate term, query failure and a successful zero count
are distinct. PubMed title/abstract query hits remain unreviewed bibliographic
proxies; no full-text or chemical-identity confirmation is implied. No final
patent or literature count is selected at this stage.

The 15 unresolved model associations retain all 58 source links. All 57 QSAR
fields and 12 Pov/LRTP values/flags remain withheld upstream. Exposure intake
never consumes model predictions; independent exposure observations are
qualified by their own identity and source evidence. The GIC issues remain
annotations and eligibility decisions; no GIC-derived score is computed.

| Output | Contents |
| --- | --- |
| `market_source_records.csv` | All 448,174 canonical rows, native identifiers, source fields, separate qualitative/numeric eligibility and exclusion reasons |
| `legacy_production_records.csv` | Selected and excluded legacy production observations with compound, field, source and value-index lineage |
| `market_gate_audit.csv` | Per-compound historical and gated presence states, eligibility counts and changes |
| `raw_file_verification.csv` | Declared and observed raw hashes, including explicit provenance gaps if present |
| `market_source_summary.csv` | Row and eligibility counts by source; counts are not unique chemicals |
| `patent_records.jsonl`, `pubmed_records.jsonl`, `pubchemlite_patent_records.jsonl` | All raw query/source records, qualifiers and exclusion reasons |
| `gic_tag_eligibility.jsonl`, `gic_compound_audit.csv` | Direct SID/tag support, matching path, frozen classification, metadata limits and missingness |
| `exposure_source_links.jsonl` | Unchanged Stage 4A exposure selection/exclusion provenance |
| `compound_exposure_evidence.csv` | Compact eligibility view with specialist decisions, identity and GIC flags; no scores |
| `identity_review_source_links.jsonl` | All original source memberships of the 15 model-review compounds |
| `exposure_field_mapping.csv`, `exposure_summary.csv`, `exposure_manifest.json` | Mappings, totals, policies, runtime and input/upstream/output fingerprints |

Validate with:

```text
python -m plastprior.validation --stage exposure-inputs --baseline PATH_TO_FROZEN_RUN --results results/stage6/6a --output-dir results/validation_stage6a
```

Validation recursively checks Stage 5B and earlier stages. It compares every
canonical source field and external raw record, preserving multiplicity, and
compares all 15,125 historical presence states and evidence counts with the
frozen historical selection audit. Intended eligibility changes are reported
separately: 21,331 identity-ambiguous market/production observations are withheld,
and 611 compound presence states change after qualification. A lower or unknown
state is not evidence of lower measured exposure. Validation also checks source
links, model isolation, GIC direct support and deterministic reconstruction.
The validation report also writes `quantity_anomalies.csv` and
`numeric_eligibility_changes.csv`. Negative Nordic SPIN quantity values remain
verbatim in the source ledger but cannot represent nonnegative quantities:
423 formerly eligible observations across 229 compounds are excluded from
numeric eligibility. Their source meaning remains unresolved; they are not
converted to zero, made positive or treated as measured negative exposure.
Qualitative presence is assessed separately. Every numeric-count difference
from the historical audit must be explained by the explicit invalid-bound
exclusions. Exposure-score agreement is intentionally outside Stage 6A. Native Windows
execution remains unverified; only the existing portable Python dependencies
are used.


## Stage 6B: exposure dimension assessment

```text
python main.py --assess-exposure
```

This runs Stages 1–6A and writes Stage 6B to `results/stage6/6b/`.
`exposure.py` implements evidence qualification, scoring and change reporting;
`exposure_policy.json` records thresholds, rules and input provenance. The
private `_exposure_reference.py` contains namespaced ports of the fingerprinted
historical functions. This compatibility layer preserves historical parsing,
source-selection order and nested audits for regression; it is not a new
workflow stage and never imports the old project. Analysis evidence must pass
Stage 6A eligibility before it can supply a score.

In addition to the Stage 6A input bundle, supply
`data/ExposureReference/20261006T233429Z/official_us_epa_production_by_cas.csv`
from the frozen Stage 6 checkpoint. Its declared hash and checkpoint membership
are verified. It is a frozen derived table used to reconstruct the historical
EPA compatibility audit; original archive-to-table transformations are not
rerun. Source archives remain fingerprinted by Stage 6A.

Five exposure dimensions have a theoretical combined maximum of 10:

| Dimension | Rule |
| --- | --- |
| Production/market scale | Positive quantity below 1,000 tonnes: 0.5; at least 1,000: 1; at least 100,000: 2. Eligible positive qualitative presence supplies 0.5 when the numeric score is absent or zero. |
| Patent activity | Count at least 1 / 1,000 / 10,000: 0.5 / 1 / 2. |
| PubMed query frequency | Count at least 1 / 5 / 20: 0.5 / 1 / 2. LitChemPlast counts remain auxiliary. |
| Food-contact/human-detection evidence | FCCmigex membership contributes 1; identity-qualified FCChumon detection contributes 1. Source membership alone is not human detection. |
| Industrial-inventory association | Eligible unique tag count at least 1 / 2 / 4: 0.5 / 1 / 2. |

**Two explicit result roles.** `exposure_historical.csv` recomputes all 63
historical exposure fields, including the full evidence JSON, source choices,
legacy EPA audit and historical zero-filling behavior. Its role is
`historical_reproduction_only`. `compound_exposure_scores.csv` preserves all
Stage 5B analysis fields and adds exposure results with role
`analysis_after_eligibility_audit`. Historical outputs are never substituted for
eligible analysis inputs.

**Selection and provenance.** Quantities are never added across sources,
jurisdictions, activities or periods. The selected proxy is the maximum eligible
historical quantity, using the reported upper bound before the lower bound.
Within-source ties use value-status priority, year and record ID; across-source
ties use value status, metric type and source ID, following the historical order.
Unknown reporting periods remain unknown, and tonnage is not silently annualised.
The ledger retains the selected parsed record ID, per-source winners, lower-ranked
candidates and exclusion reasons. Equal source counts are never summed for patents;
curated and PubChemLite evidence use the maximum count with explicit source
precedence and row/path provenance. External queries only correct a zero baseline
when the Stage 6A query qualification passes.

**Missingness and observed zero.** An unavailable component is null, not zero.
A completed zero query or inventory lookup supplies zero only for that defined
proxy; absence from a database does not establish no real-world exposure.
`Exposure_available_dimensions` counts the five dimensions, with food contact
and human detection grouped together. `Exposure_score` is present only when all
five dimensions are available. `Exposure_observed_score` sums the available
components without renormalisation and is not a complete score for ranking.
`Exposure_missing_dimensions`, component availability flags and reasons retain
the distinction. `Exposure_score_basis` lists positive available contributions
and does not certify that the total is complete.

FCChumon zero additionally requires a completed valid-CAS source lookup. The
23 rejected ambiguous-CAS associations and 331 records without a valid query
CAS are unavailable for the human-detection component, not confirmed zero.
The original resolution paths remain in the decision ledger. Food-contact
membership remains independently usable, but the joint dimension is incomplete
when the human-detection component is unavailable.

**Exceptions.** The 15 model-review associations retain all 58 memberships and
all upstream QSAR/Pov/LRTP isolation. Neither predictions nor PBMT scores enter
the exposure input view; independent exposure evidence remains eligible.
GIC name associations remain unavailable for inventory scoring, and shared-tag
associations require direct local support. All 12 directly supported inventory
tags in the shared-identifier case remain eligible. Metadata limitations persist.
Negative quantity observations remain visible but cannot supply a numeric
candidate. The frozen historical run selected none of these negative quantities,
so removing the 423 formerly eligible invalid candidates must not replace any
historical numeric winner. The qualitative identity gate is applied separately.

The 74 terminal-status patent queries with error messages remain excluded from
zero correction. This error gate already existed historically. The analysis
change is that failed correction without a positive independent fallback remains
unavailable instead of becoming zero. No-CID records and unsuccessful PubMed
queries are also distinct from validated zero counts. Curated count observations
retain their nested field paths, values and selection/rejection explanations;
PubChemLite winners link to their Stage 6A parsed-row audit IDs.

| Output | Purpose |
| --- | --- |
| `exposure_historical.csv` | Recomputed historical exposure fields; regression only |
| `compound_exposure_scores.csv` | Unchanged upstream analysis plus qualified exposure scores, coverage and missingness |
| `exposure_historical_selection.jsonl` | Reconstructed historical market-source selections and rejection counts |
| `exposure_historical_evidence.jsonl` | Complete historical nested exposure evidence |
| `exposure_analysis_decisions.jsonl` | Qualified selections, source links, gate decisions and component reasons |
| `exposure_candidate_decisions.csv` | Every canonical/legacy candidate, eligibility and selected/excluded/lower-ranked reason in both views |
| `exposure_score_changes.csv` | Every changed historical exposure field, before/after value and reason |
| `exposure_score_summary.csv` | Available, unavailable and zero results by component and view |
| `identity_review_source_links.jsonl` | All 58 memberships of the model-review cohort |
| `exposure_scoring_manifest.json` | Input/upstream, implementation, policy and output hashes; runtime and rules |

Validation:

```text
python -m plastprior.validation --stage exposure --baseline PATH_TO_FROZEN_RUN --results results/stage6/6b --output-dir results/validation_stage6b
```

Validation recursively checks Stage 6A and earlier stages; compares all 63
historical fields and nested evidence by full InChIKey; verifies the historical
market-selection audit; independently applies analysis thresholds and missingness;
and checks unchanged upstream fields, prediction isolation, source lineage,
complete change accounting and deterministic reconstruction. Numeric comparison
is exact; JSON comparison retains nesting, list order and nulls while ignoring
object-key order and equivalent numeric spelling. Identity/GIC/quantity/query
eligibility changes are reported explicitly, rather than forcing analysis scores
to reproduce unsafe historical eligibility. Stage 6B does not implement combined
hazard-exposure prioritisation or ranking. Native Windows execution remains
unverified.

For the frozen `20261006T233429Z` run, validation passed for all 15,125
compounds and 63 historical fields, including recursive evidence comparisons,
with no differences. The qualified analysis has 7,951 complete exposure totals
and 7,174 incomplete totals. All 162 tests passed. Independent command-line and
notebook execution produced 125 byte-identical output files, including 115
upstream files unchanged from the pre-6B fingerprints. Detailed local reports
are `results/validation_stage6b/exposure_scoring_validation_summary.json` and
`results/validation_stage6b/reproducibility.json`. These checks establish
reproducibility against frozen inputs; they do not independently verify the
underlying source observations.


## Stage 7A: aggregate scores, eligibility and priority tiers

```text
python main.py --assess-priority
```

This runs Stages 1–6B and writes Stage 7A to `results/stage7/7a/`. The notebook
provides the same entrypoint with a compact completeness and tier summary.
`plastprior/priority.py` performs aggregation, and `priority_policy.json`
records the weights, thresholds, historical source fingerprint and frozen-run
binding. There is no ranking or Top-N selection in this stage.

**Historical reproduction.** Join the separate Stage 5A, 5B and 6B historical
score tables by full InChIKey, rejecting duplicates, missing identities and
incompatible upstream manifests. Recompute the frozen rules:

```text
H = 2P + M + 2B + 3T
Priority = H + E
High: Priority >= 12 and H >= 4 and E >= 4
Moderate: otherwise Priority >= 6 and H >= 2 and E >= 2
Low: otherwise, for records with data
```

The historical view deliberately retains the old zero filling of unavailable
hazard components. It requires all four hazard columns and six available
historical exposure indicators, as in the frozen run; it does not invoke older
missing-column compatibility fallbacks. Under this contract, all historical
records have exposure data, so the historical `No data` priority category is
not reached. Historical hazard status still distinguishes any available PBMT
component from none. These results are labelled `historical_reproduction_only`.

**Qualified analysis.** Inherit the Stage 6B analysis table verbatim, including
component scores, availability, evidence and exposure values. Missing component
scores contribute zero only to the weighted hazard and additive exposure sums;
the raw scores remain missing and contributions are not renormalised. H and E are
numeric contribution sums even when an entire domain is unavailable. Records
with at least one available component have S = H + E and `Priority_eligible=True`.
Only records with all ten components unavailable have no total, a `No data` tier
and no rank. Domain completeness is descriptive, not an eligibility gate.

The current `priority-hgt10-ege5-v1` policy uses unrounded H and E:

```text
High: H > 10 and E >= 5
Moderate: 6 <= H <= 10 and E >= 5, or H > 10 and E < 5
Low: otherwise, for eligible records
```

`Priority_score` remains H + E; neither classification nor ranking uses display
rounding. Historical reproduction uses the frozen dual gates above through a
separate classifier. See [the migration contract](priority_classification_migration.md)
for old/new verification and independent output directories.

`Hazard_available_dimensions`, `Hazard_complete`, `Hazard_missing_dimensions`
and domain status distinguish missing contributions from observed zeros. Domain
status is `Complete`, `Partial` or `Unavailable`; priority status is `Complete`,
`Partial` or `No data`. `Priority_missing_reasons` retains component gaps, whereas
`Priority_ineligibility_reasons` applies only to assessments without any available
evidence. Malformed, negative, non-finite or out-of-range scores and contradictory
availability or aggregate values are rejected.

**Identity, GIC and exposure limitations.** The 15 unresolved model associations
retain their QSAR/Pov/LRTP isolation and all 58 source memberships. Independent
structural and database evidence remains usable. None currently has four
available PBMT components, so none receives a complete priority total. This is
a completeness decision, not deletion of the chemical or all its evidence.
GIC name-review flags, shared-association decisions and metadata limitations
remain unchanged. GIC contributes only through the already qualified exposure
inventory component; raw list labels do not add hazard or priority points.
Negative-quantity exclusions, patent query failures, valid source zeroes and
unavailable human-detection evidence retain the Stage 6B treatment. No source
selection, identity resolution, live query or model prediction is repeated.

**Audit outputs.**

| Output | Purpose |
| --- | --- |
| `priority_historical.csv` | Ten historical component scores and seven final score/status/tier fields |
| `compound_priority_assessment.csv` | Unchanged Stage 6B analysis plus aggregate scores, completeness and tiers |
| `priority_decisions.jsonl` | Historical and analysis decisions, weighted components, missing reasons, identity/GIC context and source-ledger references |
| `priority_changes.csv` | Every changed final field, old/new values and documented causes, including status-semantics changes |
| `priority_summary.csv` | Domain completeness and tier counts for each view |
| `identity_review_source_links.jsonl` | Unchanged source memberships of the 15 model-review compounds |
| `priority_manifest.json` | Policy, implementation, upstream and output hashes; counts and explicit no-ranking scope |

Decision records join to `pm_decisions.jsonl`, `bt_decisions.jsonl` and
`exposure_analysis_decisions.jsonl` by full InChIKey. Their upstream manifests
bind those files to their source observations and exclusions. The full source
ledgers remain in their original stage directories rather than being duplicated.
`priority_changes.csv` distinguishes upstream hazard-isolation changes, exposure
eligibility changes, incomplete-domain withholding and revised status semantics.
Its row count is a count of changed fields, not changed chemicals or scores.

**Validation and interpretation.**

```text
python -m plastprior.validation --stage priority --baseline PATH_TO_FROZEN_RUN --results results/stage7/7a --output-dir results/validation_stage7a
```

The validator recursively checks preceding stages, verifies the frozen seventh
stage checkpoint and compound table hashes, and compares seven historical final
fields and ten input scores for every full InChIKey. Independent arithmetic checks
use fixed historical weights and dual-gate boundaries; they verify analysis
missingness, qualification, source references, unchanged upstream fields and
complete change accounting. Deterministic replay must reproduce every Stage 7A
output. Historical parity does not require qualified analysis results to match
historical zero-filled values.

Complete-case eligibility favours compounds with more available evidence and
does not establish representativeness of the full inventory. Missing records
must remain visible alongside their available evidence. Low priority does not
mean safe; score weights and tier thresholds are screening choices, not measured
risks or probabilities. Source observations are not independently validated by
reproducing the frozen computation. Native Windows execution remains unverified.

For the frozen `20261006T233429Z` run, all 15,125 records match the historical
seven final fields and ten input scores with zero differences. Independent
analysis and deterministic-reconstruction checks also passed. There are 8,550
complete hazard totals and 4,244 complete priority assessments: 2,051 High,
1,828 Moderate and 365 Low. The other 10,881 records are `Insufficient evidence`.
Among eligible assessments, 13 priority totals and two tiers differ from the
historical view because of upstream exposure eligibility changes. All changes,
including withheld totals and revised status semantics, are documented.
All 174 tests passed. The notebook executed 15 code cells without errors;
independent notebook and command-line runs produced 132 byte-identical files,
including 125 upstream files unchanged from the pre-7A fingerprints. Local
reports are `results/validation_stage7a/priority_validation_summary.json` and
`results/validation_stage7a/reproducibility.json`.


## Stage 7B: eligible ranks and inclusive Top-N

```text
python main.py --rank-priority --top-n 100
```

This runs Stages 1–7A and writes Stage 7B to `results/stage7/7b/`. The ranking
module checks the upstream manifest, implementation and policy fingerprints,
and verifies qualification against Stage 7A. It does not change scores, tiers,
evidence, source selections, model exclusions or GIC associations.

**Ranks and ties.** All `Priority_eligible=True` records with a finite total
score enter the ranking, including partial evidence. Competition rank is one plus the number of eligible
scores strictly greater than the record's score. Equal scores share ranks,
for example 1, 2, 2, 4. Decimal comparisons precede display rounding. Descending
score and ascending full InChIKey give a reproducible display order, but the
identifier is not evidence of higher priority within a tied group.

The Top-N export includes the entire group tied with the Nth eligible record.
It can therefore contain more than N rows. A positive integer N is required;
when N exceeds the eligible pool, all eligible records are returned. With no
eligible records, the export is empty and its boundary score is null. Summary
metadata retains N, actual selected count, cutoff and boundary group size.
`Priority_tier` remains unchanged. Its hazard/exposure classification means that a
Moderate record can have a higher total than a High record; tiers do not reorder
the score ranking or break ties.

**Unranked records and limitations.** Every record remains in
`compound_rankings.csv`, including the 15 model-review compounds. Ineligible
records have null `Priority_rank`, `Priority_tie_size` and `Top_n_selected`;
null selection is not a valid negative selection within the ranked pool.
Supported zero scores remain rankable, including those with partial evidence. `unranked_review.csv` is sorted
only by InChIKey and retains component scores, missingness reasons and identity
and GIC context. Partial-evidence records with available contributions are ranked;
all-unavailable records remain unranked. GIC name-only associations do not gain
inventory-score contributions. Other GIC review flags
do not create additional exclusions beyond the qualified Stage 7A decision.

**Historical comparison and optional strict replay.** Normal runs reconstruct
historical display order by exact descending historical score and full InChIKey.
The historical input identity fingerprint, score completeness and validity remain
mandatory. `Historical_sort_position` is an ordinal in this reconstruction, not
a scientific rank or an assertion of frozen legacy tie order. The historical
CSV tables contain `Historical_order_mode`; the change audit contains
`historical_order_mode`; the ranking summary, manifest and exported database
metadata record the method, observed and expected Top-100 order hashes, and
whether those hashes match. Historical strict-N membership comparisons in portable
mode refer to this reconstruction, not verified frozen membership.

For explicit historical regression, use `--strict-historical` on the CLI or
`integrate_ranking(..., strict_historical=True)`. This retains the original pandas
quicksort and rejects any frozen Top-100 order mismatch. Matching pandas and
NumPy versions alone do not guarantee identical unstable tie order across
platforms. The strict historical validator refuses portable-mode outputs rather
than reporting them as a successful frozen replay. Both modes preserve historical
scores and derived competition ranks; neither changes the current analysis
scores, competition ranks, tie sizes or inclusive Top-N selection.

The historical validation covers full identity order, seven final fields and
ten input scores, plus the 16 overlapping score/status/tier fields in the old
Top-100. Additional legacy Top-100 names, categories, analytical annotations
and source-detail columns are explicitly listed as outside reconstruction
scope in the validation report; no full-table parity claim is made for them.

**Change accounting.** For each currently eligible record, retain three
competition ranks: historical full pool, historical scores restricted to the
current eligible pool, and current analysis. The first difference quantifies
the eligibility-pool effect; the second captures score updates within the
eligible pool, involving the record and/or its competitors. These are defined
comparison scenarios, not a unique causal attribution. Own-score changes are
flagged separately. Historical and analysis ordinal display positions are also
recorded; tied analysis groups carry an explicit identifier-display annotation,
which does not imply a change in scientific rank. A rank improvement does not itself establish stronger
evidence or greater measured risk. Membership comparison uses historical
strict Top-N versus current inclusive Top-N for the requested N; historical
Top-100 membership is also retained separately when N differs from 100.

| Output | Purpose |
| --- | --- |
| `compound_rankings.csv` | All unchanged Stage 7A fields plus qualification, ranks, ties and nullable Top-N selection |
| `eligible_priority_ranking.csv` | Compact complete-case ranking with evidence context |
| `top_priority_including_ties.csv` | Full inclusive Top-N, without truncating the boundary group |
| `unranked_review.csv` | All incomplete records, their available evidence and missing reasons |
| `historical_priority_order.csv` | Historical scores, labelled ordering mode, ordinal positions and derived tie ranks |
| `historical_top100.csv` | First 100 historical-score rows under the declared ordering mode; frozen order is enforced only in strict mode |
| `ranking_changes.csv` | Pool/score rank shifts, membership changes, reasons and Stage 7A decision references |
| `ranking_summary.json` | Eligible/unranked counts, requested N, actual size, cutoff and boundary ties |
| `identity_review_source_links.jsonl` | Unchanged 58 source memberships for the model-review cohort |
| `ranking_manifest.json` | Implementation, rules, upstream/output hashes and runtime metadata |

Strict historical validation (generate Stage 7B with `--strict-historical` first):

```text
python -m plastprior.validation --stage ranking --baseline PATH_TO_FROZEN_RUN --results results/stage7/7b --output-dir results/validation_stage7b
```

This recursively validates prior stages, checks the frozen historical artifacts,
independently counts strictly greater eligible scores, checks every boundary
member and exclusion, verifies change decomposition, permutes input rows and
reconstructs all outputs deterministically. Analysis ranks must be invariant
to input order; legacy ordinal positions intentionally follow the frozen
sorting contract. Complete-case selection favours well-characterised compounds.
The ranked subset is not the complete chemical universe, and the ranking is
a screening order rather than a precise risk estimate.

For the frozen `20261006T233429Z` run, validation passed with zero differences
in historical Top-100 membership, order and 16 overlapping migrated fields.
All preceding stages, independent ranks, boundary membership, exclusion reasons,
change decomposition, permutation invariance and deterministic reconstruction
also passed. The analysis ranks 4,244 compounds and leaves 10,881 unranked.
Requested Top-100 includes 107 compounds: the cutoff is 19.5 and all 22 members
of its boundary tie group are retained. Relative to the historical strict
Top-100, 22 records enter and 15 leave. Those 15 departures are incomplete
assessments and are not the separate 15-member model-identity-review cohort.
All 183 tests passed. The notebook executed 16 code cells without errors;
independent notebook and command-line runs produced 142 byte-identical files,
including 132 upstream files unchanged from pre-7B fingerprints. Retained historical reports
are located at
`results/verification/historical_regression/ranking_validation_summary.json` and
`results/verification/historical_regression/reproducibility.json`.
The command above writes a new validation run to its specified output directory;
it does not replace the retained historical reports.
