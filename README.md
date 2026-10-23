# PlastPrior

PlastPrior is being developed as a framework integrating hazard and exposure
evidence to prioritise plastic-associated chemicals. The current implementation
inspects local inputs, assembles source inventory records, resolves chemical
identities and aggregates records by full structure-derived InChIKey. Stage 3A
also integrates the frozen VEGA predictions with explicit identity-review
flags. Stage 3B reproduces historical Pov/LRTP calculations and isolates
unverified identities from analysis outputs. Stage 4A assembles basic source
evidence with explicit field mapping and selection/exclusion audits. Stage 4B
adds LitChemPlast associations and FCChumon human-detection evidence. Stage 4C adds
NORMAN analytical-platform predictions and GIC regulatory-list associations. Hazard, exposure and priority
scores are not implemented.

## Input inspection

`plastprior/inputs.py` is the single implementation used by `main.py` and
`PlastPrior.ipynb`. It reads the 12 declared source files, checks the required
column labels, and reports dimensions for 14 selected source-native tables:
two identity-reference tables, 11 inventory tables, and one literature-to-chemical
link table. The catalog is `plastprior/sources.json`.

The notebook contains Setup, Stage 1, Stage 2 and Stage 3A/3B/4A/4B/4C, with ten code cells. It displays
file versions, table dimensions, inspection outcomes, source record counts,
identifier availability, identity-resolution outcomes, model coverage, QSAR
identity exceptions, historical LRTP calculation coverage and analysis exclusions. Full provenance notes, references,
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
    identity.py
    qsar.py
    lrtp.py
    evidence.py
    _evidence_rules.py
    evidence_specialists.py
    evidence_annotations.py
    validation.py
    sources.json
    identity_baseline.json
    qsar_models.json
    lrtp_parameters.json
    evidence_fields.json
    evidence_specialists.json
    evidence_annotations.json
  tests/
    test_inputs.py
    test_source_records.py
    test_identity.py
    test_qsar.py
    test_lrtp.py
    test_evidence.py
    test_specialist_evidence.py
    test_annotations.py
    test_validation.py
  data/                     # Local inputs; ignored by Git
  results/                  # Generated reports; ignored by Git
```

The `plastprior` package holds the scientific implementation. The command line
and root-level notebook use the same functions. Tests are versioned source code;
their temporary fixtures do not require or alter the research collection.

The planned sequence is input validation and ingestion, chemical identity
resolution, QSAR evidence integration, evidence assembly, hazard assessment,
exposure assessment, and chemical prioritisation. Stages 1 and 2, frozen-report
QSAR integration (3A), and historical Pov/LRTP calculation with identity isolation
(3B), basic source evidence assembly (4A), and specialist literature/human-detection
evidence (4B), and analytical/regulatory annotations (4C) are implemented. Later stages will be introduced incrementally with
corresponding validation.

## Source record assembly

`build_source_records()` in `plastprior/inputs.py` assembles the 11 candidate
inventory tables using explicit `record_mapping` declarations in `sources.json`.
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
in `sources.json` explicitly select their fields:

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
R, RDKit and the VEGA application are not required for input inspection alone.
Stage 2 requires the pinned RDKit 2026.3.1 release, including its InChI support.
The identity module checks that version before running; use the project virtual
environment and install `requirements.txt` if it differs. No VEGA application is
needed for Stage 2.

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

During Stage 1, the five supporting groups receive **presence checks only**. The checks require
20 named VEGA reports, named GIC/patent/literature files, and the production
manifest plus its eight source directories. They do not certify report contents,
all nested production files, or readiness for a future scoring workflow. The
recursive file totals include any supplementary backups present in those folders.
Missing supporting inputs are reported separately from Stage 1 source failures.
Each later stage must validate the auxiliary inputs it actually uses before
performing its calculations. Stage 3A validates the content and fingerprints of
the 20 VEGA reports when `--integrate-qsar` is requested.

## Run

Command line, on macOS or Windows:

```text
python main.py
python main.py --data-root "path to an external data directory"
python main.py --require-supporting-inputs
python main.py --assemble-records
python main.py --resolve-identities
python main.py --integrate-qsar
python main.py --calculate-lrtp
python main.py --integrate-evidence
python main.py --integrate-specialists
python main.py --integrate-annotations
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

`--assemble-records` adds record assembly after the requested inspection checks
pass. It writes the following files under `results/stage2/` (or the specified
output directory):

| File | Contents |
| --- | --- |
| `source_records.csv` | All inventory records, provenance, selected fields and exclusion reasons |
| `source_record_summary.csv` | Per-table counts, included-record availability and reader warnings |
| `source_field_mapping.csv` | Explicit table scopes, field lists and inclusion requirements |
| `source_record_manifest.json` | Policy, runtime, input and output fingerprints |

The notebook calls the same assembly function before identity resolution.
`--assemble-records` stops after assembly; `--resolve-identities` also performs
identity resolution and aggregation. When reading the exported records
programmatically, use `dtype=str, keep_default_na=False`
to retain textual native IDs and literal placeholders; interpret `included`
explicitly as the strings `True` or `False` when using this read mode.

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
