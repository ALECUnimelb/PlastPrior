# Publication readiness review

> Current scoring-policy update: [zero-contribution policy](zero_contribution_policy.md)
> supersedes the complete-domain eligibility rule and its recorded 4,244/10,881
> verification counts below. Those dated results describe the earlier export,
> not the repaired candidate. Upstream evidence admission remains unchanged.


Current local storage: see [retained results and verification records](results_layout.md). Evidence files were relocated without changing their bytes. Historical paths and removed stage-output locations are documented in the migration manifest; the review findings below remain unchanged.

Review date: **23 October 2026 (Australia/Melbourne)**. Scientific code baseline:
`9e211e8bf3f71506629ca6f4c5f42428816e7aa3` (Stage 7B).

**Status: review complete; publication preparation remains pending.** This is
an inventory and gap assessment, not permission to redistribute source data,
a public release, a new scientific validation or a claim of independent
clean-environment reproduction. No scoring rules, source data or stage outputs
were changed for this review.

The machine-readable [publication inventory](publication_inventory.json)
records committed code hashes, local input/output hashes, source declarations,
observed dependencies and validation-report references. Its code section refers
to committed bytes at the baseline above, excluding these new review documents
and their README link. Future release preparation must regenerate the inventory
against the final selected revision; this document is not a permanent lock file.

Follow-up: the [data access and provenance review](data_access_review.md) records
subsequent external-source checks, including four differences between local
workbooks and candidate official archives. The findings below describe the
initial local review; the follow-up does not replace its frozen inventory.

## Evidence available now

| Item | Locally confirmed evidence | Limit of the claim |
| --- | --- | --- |
| Scientific code | 53 committed files inventoried at the baseline revision | Attribution, licence selection and release metadata remain pending |
| Main input collection | 12 files, approximately 424.3 MB; freshly calculated hashes match the source inspection report | Matching local bytes does not authenticate the publisher's version or grant redistribution rights |
| Auxiliary inputs | 5 declared groups containing 25 required files; file presence, byte sizes and hashes recorded | Required subdirectory presence does not inventory or verify every raw file inside it |
| Frozen reference inputs | 8 files under `data/ExposureReference/20261006T233429Z/`; hashes match declared policy | Some are historical derived tables, not independently rebuilt raw-source transformations |
| Stage results | All 142 validated output files freshly hashed; all match recorded validation fingerprints | These are local outputs, not a deposited publication archive |
| Validation | 12 recursive validation summaries report `passed`; Stage 7B reproducibility report passed | This review checks the reports and output integrity; it does not rerun the scientific pipeline |
| Tests and notebooks | Previous implementation verification recorded 183 passing tests and 16 executed notebook code cells; source notebook has no stored outputs | Unit tests were not rerun for this documentation-only review |
| Environment | Python 3.12.13, pandas 3.0.2, NumPy 2.5.4; 101 installed distribution versions recorded | An observed package list is not a complete, portable installation lock |

The 142 stage outputs total **5,870,931,352 bytes (approximately 5.87 GB)**,
excluding additional HTML/notebook exports and validation reports. This is not
the compressed size of a proposed archive. Duplicate command-line runs and
intermediate files should not be copied wholesale into a publication package.

## File disposition

“Retain” identifies a proposed package component, not final publication clearance.
Exclusion from the public package does not authorise deleting local originals.

| Files or group | Proposed disposition | Required review or action |
| --- | --- | --- |
| `main.py`, `plastprior/*.py`, `plastprior/*.json` | Retain in code release | Preserve provenance and policy fingerprints; confirm ownership, upstream attribution and selected code licence |
| `tests/*.py` | Retain in code release | Retain scientific boundary and regression tests; do not exclude tests as generated artifacts |
| `requirements.txt`, `.gitignore` | Retain in code release | Add verified environment specification later; preserve ignored data/results boundaries |
| `PlastPrior.ipynb` | Retain as the unexecuted source notebook | Verify output-free form and relative/configurable paths |
| `README.md`, `docs/publication_review.md`, `docs/publication_inventory.json` | Retain as documentation | Update baseline, claims and inventory when preparing the final release |
| Twelve `data/SourceDatabase/` files | External data package or exact-snapshot acquisition instructions, subject to permission review | Confirm dataset-specific terms, version, citation, acquisition provenance and external accessibility |
| Frozen VEGA, GIC, patent and literature query files | External reproduction inputs, subject to review | Record software/model/query versions and provenance; confirm the scope of permitted redistribution |
| Official production/market raw inputs | External reproduction inputs, subject to review | Expand the raw-file inventory from existing source manifests and establish the source-specific acquisition chain |
| `data/ExposureReference/20261006T233429Z/` | Required external inputs for current frozen reproduction | Retain all eight reference/provenance files and hashes; clearly label derived tables |
| One selected set of stage outputs and provenance manifests | Candidate for a versioned research archive | Select minimal and complete bundles, check content/permissions and preserve all required audit links |
| `results/verification/notebook_run/PlastPrior.executed.ipynb` | Candidate human-readable supplements | Link to the selected code/input/result revision; inspect for local paths or other unintended metadata |
| `results/verification/historical_regression/` reports | Candidate validation supplement | Include comparison scope and explicit exclusions; distinguish historical reproduction from qualified analysis |
| `results/cli_validation/`, superseded runs and duplicate notebook exports | Exclude from the publication package unless needed for a documented validation purpose | Superseded generated runs were removed by the approved cleanup; retain the selected final package and verification records |
| `.git/`, `.venv/`, caches, `.DS_Store`, temporary logs and workspace dumps | Exclude from the publication package | Do not package a raw workspace archive; retain installation instructions instead of a virtual environment |
| Future `LICENSE`, `CITATION.cff`, data-access instructions and environment specifications | Needed but not created by this review | Confirm licence, contributors, citation metadata, data routes and environment choices before authoring definitive claims |

The current `/data/` and `/results/` Git exclusions are appropriate for separating
the code repository from large local collections. They do not establish that
readers can obtain the inputs or reproduce the work from the public repository.

## Source provenance and access review

The following values come from `plastprior/sources.json`. They are declarations,
not newly authenticated publisher metadata. References in the JSON inventory
were copied from that catalog and were not visited or checked for current terms
during this local review. **Redistribution permission and access to the exact
snapshot remain unverified for every source below.**

| Source | Declared version | Declared snapshot date | Main provenance gap |
| --- | --- | --- | --- |
| NORMAN SusDat | 2025-06-03 export | 2025-06-03 | Filename-derived date; separate retrieval provenance not recorded |
| PubChemLite | Not recorded | Not recorded | Identify and cite the exact frozen release |
| PlastChem | 1.01 | Not recorded | Confirm release/citation correspondence and acquisition provenance |
| UNEP | 2023 | Not recorded | Report year does not identify the local workbook snapshot |
| NORMAN MPLEACH | S133 | Not recorded | Confirm exact export and access record |
| FCCmigex | Not recorded | Not recorded | Identify and cite the exact frozen export |
| FCChumon | Not recorded | Not recorded | Identify and cite the exact frozen export |
| FCCprio | 0.2 | 2026-01-15 | Confirm the file/date/release association against source evidence |
| LitChemPlast | Not recorded | Not recorded | Distinguish article citation from the exact dataset file/version |
| ICCA | Not recorded | Not recorded | Record exact export, acquisition method and source terms |
| UCSF | Not recorded | Not recorded | Distinguish the cited article from the frozen supplementary workbook |
| PlasticMAP | S1 | 2021-06-11 | Confirm the declared supplement/date and acquisition provenance |

Six sources lack a recorded version; nine lack a recorded snapshot date. Do not
fill these gaps from filesystem modification times or silently replace frozen
inputs with current downloads: either action would weaken provenance or break
the exact historical comparison. If the original metadata cannot be recovered,
retain the limitation and identify the frozen bytes explicitly.

For each required input, the eventual data-access register should contain:
source owner, dataset citation/version, retrieval evidence/date, exact file or
archive identity, SHA-256, applicable terms and evidence of permission where
needed, approved distribution/acquisition route, and any controlled-access
contact or access conditions. A citation URL or a public download alone must
not be labelled as proof of redistribution permission in this register.

## Risks and acceptance criteria

Ratings describe project impact and review priority, not numerical probability.
Maintainer/scientific-lead roles below are proposed responsibilities, not named
individual assignments or completed approvals.

| ID | Priority | Finding and consequence | Acceptance criterion / next action | Suggested owner |
| --- | --- | --- | --- | --- |
| R01 | High | The code excludes local data/results; an exact public input acquisition route has not been demonstrated | A separate reader can obtain every required frozen input by a documented approved route and pass hash checks | Data steward / maintainer |
| R02 | High | No tracked `LICENSE` or `CITATION.cff`; code attribution and source-data redistribution terms remain unverified | Confirm code ownership/licence, dependency and ported-code notices, dataset-specific terms and actual citation metadata; do not infer authors from commit counts | Project leads |
| R03 | High | Direct requirements are pinned, but the transitive environment is not locked; current NumPy differs from the old run | Create and test a reproducible environment specification; record any platform differences and the exact scope of numerical/tie-order parity | Maintainer |
| R04 | High | Only 4,244 of 15,125 compounds (28.1%) enter the analysis ranking | State the denominator and complete-case selection rule; review missingness by source and evidence profile; keep all 10,881 unranked records visible | Scientific leads |
| R05 | High | Historical agreement does not establish source correctness or validity of weights, thresholds and proxy interpretation | State the scope of historical validation; separately design and review robustness/sensitivity analyses before changing scientific assumptions | Scientific leads |
| R06 | High | Frozen exposure tables are required, but their complete raw-source transformation chain is not independently rebuilt | Either distribute the frozen derived inputs with clear scope and provenance, or separately rebuild and validate the raw transformations; do not claim raw-data end-to-end reproduction prematurely | Data steward / maintainer |
| R07 | Medium–high | Fifteen model-identity anomalies and GIC association/metadata limitations remain unresolved | Retain quarantine, source links and reason codes; document allowed independent evidence. Resolution requires supporting evidence, not deletion of flags | Scientific leads |
| R08 | Medium–high | Native Windows and a clean installation without the existing environment have not been verified; no tracked CI workflow was found | Verify basic startup and the chosen reproduction scope on fresh macOS and Windows environments; document separately what can run without the private input collection | Maintainer |
| R09 | Medium | Historical Top-100 validation covers order and 16 migrated fields; other legacy annotation columns are outside that comparison | Keep the field-scope exclusions visible. Decide whether additional annotations are needed for the manuscript before migrating or claiming their parity | Scientific leads |
| R10 | Medium | Local outputs total about 5.87 GB before supplements; a raw workspace archive would include duplicates and possibly machine-specific metadata | Design a canonical code/data/results package with a manifest, reviewed metadata, stable links and no caches or duplicate runs | Maintainer / data steward |
| R11 | Medium | No final research archive identifier, author list or journal-specific submission package has been established | Confirm authors/contributors, required method/tool-use disclosures, citation metadata and deposition destination before making a final release | Project leads |

R07 does not require accepting disputed predictions or dropping entire compounds
to make progress. Publication may retain a clearly scoped quarantined analysis;
the scientific leads must decide whether that limitation supports the intended
claims. Similarly, historical metadata that cannot be recovered must remain
unrecorded rather than being invented to complete a checklist.

## Recommended next work packages

1. **Exact-input access and rights register.** Complete source-by-source access,
   citation and permission evidence; expand the supporting/raw-input inventory.
   Deliver a clear list of shareable files, acquisition-only files and unresolved
   files. Do not upload data while those decisions remain unresolved.
2. **Clean-environment reproduction.** Specify and test environments in fresh
   directories, with no imports from the old project or reliance on the current
   virtual environment. Test startup, data-free tests, the selected full run,
   notebook execution and frozen comparison. Verify Windows separately.
3. **Scientific robustness plan.** Review missingness/selection effects and
   propose weight, threshold and Top-N sensitivity scenarios. Keep the validated
   main analysis frozen; new scenarios require explicit policy versions and
   interpretation rather than silent replacements.
4. **Publication assembly.** After the above decisions, prepare a versioned
   code release, approved data/acquisition package, canonical research outputs,
   validation supplement and manuscript methods/citation metadata.

Package 1 has a modest documentation/engineering workload but may require
external responses. Package 2 is a moderate technical task. Raw-transformation
reconstruction and new scientific robustness analyses may be substantially
larger and should receive separate implementation plans. No additional scoring
stage is introduced by these publication work packages.

## Release gate checklist

- [x] Inventory the current committed scientific code baseline.
- [x] Record declared primary and supporting inputs and frozen references.
- [x] Recheck all 142 validated stage-output fingerprints without changing them.
- [x] Separate historical reproduction, qualified analysis and unranked records.
- [x] Record limitations and concrete acceptance criteria.
- [ ] Confirm code licence, upstream attribution, source-data terms and citations.
- [ ] Demonstrate external access to every required exact input snapshot.
- [ ] Verify a fully specified clean environment and native Windows scope.
- [ ] Review complete-case selection bias and the intended scientific claims.
- [ ] Approve any additional raw-source reconstruction or sensitivity work.
- [ ] Select and inspect a canonical publication package, including metadata.
- [ ] Bind final code, approved inputs, environment, reports and archive identifiers.

This review leaves the existing Git history, scientific policies and data
unchanged. It does not create a licence, invent authorship metadata, publish an
archive or certify that unresolved publication gates have been satisfied.
