# Data access and provenance review

Follow-up: the [current P0 distribution checklist](data_distribution_checklist.md)
adds source-specific acquisition, citation and distribution decisions. The dated
findings below are preserved; use the follow-up for the latest assessment.

Current local storage: see [retained results and verification records](results_layout.md). Evidence files were relocated without changing their bytes. Historical paths and removed stage-output locations are documented in the migration manifest; the review findings below remain unchanged.

Review date: **23 October 2026 (Australia/Melbourne)**.
Baseline: `17ad5e1` (publication inventory); scientific baseline: `9e211e8`.

This first-pass review establishes a [source register](data_access_register.json)
covering 12 primary sources, four supporting sources, eight production/market
sources and one frozen reference bundle. It records official access routes,
licence observations, local hashes and unresolved actions. It does not replace
inputs, change scoring, resolve chemical identities or approve a public release.

Follow-up: the [read-only workbook comparison](workbook_comparison.md) found no
scientific cell-value or stored-formula differences in the four candidate pairs.
Byte differences remain recorded; acquisition history and distribution decisions
are still unresolved. The findings below retain the scope of the initial access
review.
The earlier [publication inventory](publication_inventory.json) remains a dated
baseline; this review adds new external evidence without rewriting it.

## Principal finding: four official-file comparisons differ

Four candidate official files were downloaded into the ignored local review
directory, separately from `data/`. Each download matches its publisher's MD5.
Each differs in SHA-256 from the corresponding frozen local input. Full hashes,
byte sizes, download URLs and comparisons are retained in the source register.

| Local source | Candidate official archive | Observed record-level licence | Exact-byte result |
| --- | --- | --- | --- |
| PlastChem | [Version 1.01, record 15397723](https://zenodo.org/records/15397723) | CC BY-NC 4.0 | Different |
| MPLEACH | [S133.0.1.0, record 18157912](https://zenodo.org/records/18157912) | CC BY 4.0 | Different |
| FCCprio | [Version 0.2, record 17199870](https://zenodo.org/records/17199870) | CC BY 4.0 | Different |
| LitChemPlast | [v20240809, record 13271346](https://zenodo.org/records/13271346) | CC BY 4.0 | Different |

The licence identifiers were read from the official Zenodo API records linked
in the register. These are observations about the candidate archives, not a
conclusion about the exact local files or a licence for the combined project.
[CC BY](https://creativecommons.org/licenses/by/4.0/) requires attribution and
indication of changes; [CC BY-NC](https://creativecommons.org/licenses/by-nc/4.0/)
also limits use to noncommercial purposes. Package-specific applicability and
required notices remain to be established.

**Byte differences do not establish differences in chemical values.** Possible
causes include workbook metadata, re-saving, local edits or an alternate release.
None has been established here. Historical validation remains a comparison
against the frozen local inputs; it does not authenticate their relationship to
publisher originals. Do not replace those inputs or describe them as unmodified
official downloads until the differences are explained.

The FCCprio catalog DOI is a concept-level reference that currently resolves to
version 1.0. The corresponding version 0.2 record was located through the official
version history. The local catalog has not been altered. The PlastChem record
also contains differing publication-date declarations (header/API versus release
notes); neither establishes when the local file was retrieved.

## Primary-source access register

All twelve exact local snapshot routes remain unresolved. A retrievable landing
page is not proof of access to a particular historical file. A failed tool request
does not prove that the source is unavailable or that reuse is prohibited.

| Source | Evidence obtained in this pass | Remaining action |
| --- | --- | --- |
| NORMAN SusDat | Catalog endpoint did not return usable content | Recover exact export, retrieval evidence and contributing-list terms |
| PubChemLite | [Official website](https://pubchemlite.lcsb.uni.lu/) provides citations and a current Zenodo route | Match the undated local CSV to its frozen release; do not substitute the current release |
| PlastChem | Versioned record, licence metadata and verified official download | Explain workbook differences and establish local derivation |
| UNEP | Report URL redirected to a PDF that the tool could not retrieve | Identify the workbook supplement, its provenance and applicable terms |
| MPLEACH | Versioned record, licence metadata and verified official download | Explain workbook differences and confirm the list version actually used |
| FCCmigex | [Official page](https://foodpackagingforum.org/resources/databases/fccmigex) links the NORMAN S112 chemical list | Identify exact S112 export and terms; distinguish list from full database |
| FCChumon | [Official page](https://foodpackagingforum.org/resources/databases/fcchumon) links its 2024 study; publisher retrieval failed | Match the local S1/S2 workbook to a supplement and its terms |
| FCCprio | Exact version 0.2 archive located; verified official download | Explain differences and use a version-specific reference in future acquisition instructions |
| LitChemPlast | Versioned XLS archive located; verified official download | Explain local renamed-file differences before assigning a release version |
| ICCA | [Official description](https://plasticscircularity.org/additives/) identifies multiple upstream sources | Recover CSV export method/date and source-specific terms |
| UCSF study workbook | DOI/publisher retrieval did not return usable content | Confirm exact supplement, citation and applicable terms |
| PlasticMAP | Publisher retrieval returned HTTP 403 | Confirm exact supplement and local provenance; retain filename-derived date as an inference |

The six missing version declarations and nine missing snapshot dates in the
original catalog have not been filled from candidate matches or filesystem dates.
This review's date is recorded separately from historical acquisition dates.

## Supporting and production evidence

The register retains all 20 VEGA report hashes, two GIC file hashes, patent and
literature query-output hashes, and eight frozen exposure reference/provenance
hashes. Together with the twelve main inputs, **44 frozen files were freshly
checked against the prior inventory, with no differences**.

VEGA application/model versions and report-generation provenance need further
documentation. The GIC pinned [software licence](https://github.com/envris/global-inventory-compiler-public/blob/9487e9395ee51f7cce304ff65a041854d908211d/LICENSE)
is BSD-3-Clause; this does not establish the rights for each compiled upstream
list or the local metadata table. [NCBI's policy](https://www.ncbi.nlm.nih.gov/home/about/policies/)
identifies contributed material with possible third-party terms, including in
PubChem. Query counts, parameters, dates and errors must be documented separately
from any redistribution of abstracts or full-text material.

All **42,157 files (1,164,226,573 bytes)** under the production/market root were
inventoried and hashed, including backups. The 13 entries in the root source
manifest and 32 entries in the frozen input manifest all match their declared
SHA-256 values (**45 manifest-entry checks**, with overlapping paths).
This is not a claim that every raw response was reconciled against its request
audit or that every file is necessary to reproduce the analysis.

| Source directory | Files | Current external evidence / next review |
| --- | ---: | --- |
| US EPA CDR | 16 | [Official download page](https://www.epa.gov/chemical-data-reporting/access-cdr-data) reviewed; establish exact archive access and applicable notices |
| ECHA REACH | 4,789 | Legal-notice retrieval returned HTTP 403; review export/API-response terms and exact frozen access |
| Nordic SPIN | 14,219 | Query-page retrieval timed out; retain CAS-specific response provenance and establish terms |
| Japan METI/J-CHECK | 22,822 | Official search page retrieved; reconcile raw responses and source-specific terms |
| South Korea chemical statistics | 39 | Official statistics interface retrieved; distinguish aggregate evidence from compound-level quantities |
| Canada CEPA section 71 | 105 | Catalog retrieval unsuccessful; local file-index records provide acquisition leads |
| South Korea new chemicals | 52 | Official notice page retrieved; review attachment-specific access and reuse evidence |
| Taiwan toxic chemicals | 21 | Both [quantity](https://data.moenv.gov.tw/dataset/detail/TOXIC_P_19) and [CAS mapping](https://data.moenv.gov.tw/dataset/detail/TOXIC_P_23) pages link the [Open Government Data License 1.0](https://data.gov.tw/license); frozen-file mapping and attribution remain pending |
| Canada backup directory | 93 | Propose exclusion from the release package, after checking required references; retain locally |
| Root source manifest | 1 | Collection-level date differs from some file-level retrieval dates; retain both |

Full per-file detail is saved locally in
`results/verification/publication_review/supporting_file_inventory.json`. Its SHA-256 and group
summaries are recorded in the tracked register. The detailed file is not included
in Git and is not yet an externally accessible supplement. File roles are
path-based candidates, not verified dependency decisions. Raw API/query caches
may be essential provenance; do not treat them like disposable Python caches.

The production manifest's collection date is 2026-07-13, while three entries have
retrieval timestamps on 2026-07-21. Preserve file-level timestamps and flag the
collection metadata for clarification; do not force a single date on all files.

## Disposition and next action

No exact local data bundle has completed both access and rights review. For now:

- **Potential acquisition or redistribution candidates:** the four versioned
  Zenodo archives and the Taiwan datasets have licence evidence, with local
  correspondence and notices still to establish.
- **Unresolved:** remaining sources and the combined frozen reference bundle.
  Do not label them prohibited or acquisition-only without supporting evidence.
- **Proposed package exclusions:** the backup directory and operational logs,
  subject to dependency review. No local files were removed.

The **read-only comparison of the four different workbooks** proposed by this
initial review is now complete; see the [comparison report](workbook_comparison.md).
It found equivalent scientific tables and stored formulas, with presentation and
metadata differences retained explicitly. Acquisition and editing history remain
unresolved. Continue the source-access and attribution work while preserving the
frozen inputs. Any future input adoption would require an explicit versioned
analysis and full regression comparison.

The fifteen model-identity anomalies, GIC review flags, missing-value handling,
historical/analysis separation and ranking rules remain unchanged. This pass
did not rerun scientific tests or the pipeline. Its validation concerns file
integrity, manifest consistency and documentation only.
