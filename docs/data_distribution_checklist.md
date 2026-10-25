# Data acquisition, citation and distribution checklist

Review date: **2026-10-24 (Australia/Melbourne)**. Code/document baseline: `48d94ca`.

This review covers **25 source groups**: 12 primary sources, four supporting
sources, eight production/market sources and one frozen exposure bundle.
It records evidence and release dispositions, without replacing inputs,
recomputing results or publishing files. The [machine-readable register](data_access_register.json)
retains original file hashes and historical observations; its
`p0_distribution_review` fields and `current_distribution_review` are the current assessment.

## Decision summary

| Category | Meaning | Source groups |
| --- | --- | ---: |
| A: public under conditions | A named official dataset/deposit has an explicit reuse licence. Apply its attribution, change-notice and other terms. | 10 |
| B: original source for now | Provide the provider route instead of mirroring local data until the applicable scope is established. This is not a declaration that copying is prohibited. | 9 |
| C: confirmation required | Content-specific rights/provenance remain unresolved; a related software or article licence is insufficient. | 6 |

**No complete local frozen bundle is marked release-ready yet.** Category A
identifies a licensed official object, not an authenticated match to every local
file. A missing retrieval date or different hash does not itself cancel a
licence; it prevents an unsupported claim of an exact, unmodified official copy.
Where an open licence covers the material and intended use, no additional
permission request is required solely to repeat that grant.

CC BY 4.0 permits sharing/adaptation subject to attribution, licence linkage and
change notices; CC BY-NC 4.0 adds a noncommercial condition. An openly accessible
GitHub repository does not make NC material unrestricted. These are scope
summaries of the [CC BY](https://creativecommons.org/licenses/by/4.0/) and
[CC BY-NC](https://creativecommons.org/licenses/by-nc/4.0/) terms, not a new licence
for PlastPrior or a blanket grant for third-party content.

## Source-by-source decisions

The evidence column links official providers, repositories or publisher metadata.
Failed direct retrievals and indexed-page observations are distinguished in the
individual entries below. Review dates are not historical acquisition dates.

| Source | Disposition | Observed terms and scope | Evidence |
| --- | --- | --- | --- |
| NORMAN SusDat | B: original source for now | No dataset-wide redistribution licence established in the retrieved export page. The aggregate SusDat export and contributing lists require separate scope review. | [Evidence 1](https://www.norman-network.com/nds/susdat/); [Evidence 2](https://www.norman-network.net/nds/SLE/) |
| PubChemLite | A: public under conditions | CC BY 4.0 on candidate record 22953182. Applies to the identified PubChemLite-CCSbase-20260925 deposit; the local undated CSV has not been matched. | [Evidence 1](https://pubchemlite.lcsb.uni.lu/); [Evidence 2](https://zenodo.org/records/22953182); [Evidence 3](https://zenodo.org/api/records/22953182) |
| PlastChem | A: public under conditions | CC BY-NC 4.0 on version 1.01, record 15397723. The official version permits attributed noncommercial sharing/adaptation; this does not establish an unrestricted licence for the combined database. | [Evidence 1](https://zenodo.org/records/15397723); [Evidence 2](https://zenodo.org/api/records/15397723) |
| UNEP | B: original source for now | No licence for the exact annex workbook established in this review. The report and its Excel annex are distinct objects; report access alone does not clear the local workbook. | [Evidence 1](https://www.unep.org/resources/report/chemicals-plastics-technical-report); [Evidence 2](https://www.unep.org/pt-br/node/34317) |
| MPLEACH | A: public under conditions | CC BY 4.0 on NORMAN-SLE-S133.0.1.0, record 18157912. The identified MPLEACH deposit permits attributed sharing/adaptation; local byte differences remain provenance issues. | [Evidence 1](https://zenodo.org/records/18157912); [Evidence 2](https://zenodo.org/api/records/18157912) |
| FCCmigex | A: public under conditions | CC BY 4.0 on candidate NORMAN-SLE-S112.0.2.1, record 15852269. Covers the deposited S112 list, not automatically the whole interactive FCCmigex database. Candidate XLSX MD5 differs from the local workbook. | [Evidence 1](https://foodpackagingforum.org/resources/databases/fccmigex); [Evidence 2](https://zenodo.org/records/15852269); [Evidence 3](https://zenodo.org/api/records/15852269) |
| FCChumon | C: confirmation required | CC BY 4.0 observed on the publisher article; third-party exceptions remain possible. The article links Supplementary Tables, but the exact local S1/S2 workbook-to-supplement relationship and notices have not been checked. | [Evidence 1](https://foodpackagingforum.org/resources/databases/fcchumon); [Evidence 2](https://www.nature.com/articles/s41370-024-00718-2?trk=public_post_comment-text); [Evidence 3](https://www.nature.com/articles/s41370-024-00718-2.pdf) |
| FCCprio | A: public under conditions | CC BY 4.0 on version 0.2, record 17199870. The identified version permits attributed sharing/adaptation; the concept DOI is not a version pin. | [Evidence 1](https://zenodo.org/records/17199870); [Evidence 2](https://zenodo.org/api/records/17199870) |
| LitChemPlast | A: public under conditions | CC BY 4.0 on v20240809, record 13271346. The identified XLS/relational deposit permits attributed sharing/adaptation; local XLS bytes differ although scientific tables matched. | [Evidence 1](https://zenodo.org/records/13271346); [Evidence 2](https://zenodo.org/api/records/13271346) |
| ICCA | B: original source for now | No redistribution permission for the local CSV established. The provider describes registration-based access and multiple upstream contributions, including industry sources. | [Evidence 1](https://plasticscircularity.org/additives/); [Evidence 2](https://iccadatabase.com/) |
| UCSF | A: public under conditions | CC BY-NC 4.0 on official supplement doi:10.1021/envhealth.5c00197.s001. Covers the identified ACS Figshare supplement (version 1); it has a different MD5 and size from UCSF paper database.xlsx. Scientific equality was not tested. | [Evidence 1](https://api.figshare.com/v2/articles/31072267); [Evidence 2](https://acs.figshare.com/articles/dataset/Unraveling_Plastic-Related_Chemical_Exposures_during_Pregnancy_and_Their_Associations_with_Pregnancy_Outcomes_Using_Suspect_Screening_Analysis/31072267) |
| PlasticMAP | A: public under conditions | CC BY-NC 4.0 on official supplement doi:10.1021/acs.est.1c00976.s001. Covers the identified ACS Figshare ZIP deposit (version 1); the archive-to-local-workbook mapping has not been verified. | [Evidence 1](https://api.figshare.com/v2/articles/14794556); [Evidence 2](https://acs.figshare.com/articles/dataset/Deep_Dive_into_Plastic_Monomers_Additives_and_Processing_Aids/14794556) |
| Frozen VEGA reports | C: confirmation required | GPL 3 reported for VEGA QSAR software; report-content scope not established. A software licence does not alone determine the rights in generated predictions, report templates or embedded reference/training material. No claim is made that outputs inherit GPL. | [Evidence 1](https://www.vegahub.eu/download/vega-qsar-download/); [Evidence 2](https://www.vegahub.eu/download/vega-qsar-download-versions/); [Evidence 3](https://www.vegahub.eu/portfolio-item/vega-qsar/) |
| GIC inventory | C: confirmation required | BSD-3-Clause confirmed for the pinned GIC code only. Compiled upstream inventories and local gic_list_tag_metadata.csv have separate provenance and rights requirements. | [Evidence 1](https://github.com/envris/global-inventory-compiler-public/blob/9487e9395ee51f7cce304ff65a041854d908211d/LICENSE); [Evidence 2](https://github.com/envris/global-inventory-compiler-public) |
| Patent query evidence | C: confirmation required | NCBI policy distinguishes government-created information from contributed/licensed material. The local CSV header describes counts, query/provenance/status fields, not an abstract/full-text collection. This header check is not a complete rights or content audit. | [Evidence 1](https://www.ncbi.nlm.nih.gov/home/about/policies/) |
| Literature query evidence | C: confirmation required | NCBI policy distinguishes government-created information from contributed/licensed material. The local CSV header describes counts, query/provenance/status fields, not an abstract/full-text collection. This header check is not a complete rights or content audit. | [Evidence 1](https://www.ncbi.nlm.nih.gov/home/about/policies/) |
| US EPA Chemical Data Reporting | B: original source for now | Official CDR/IUR downloads available; dataset-specific applicability of reuse notices remains to verify. The EPA disclaimer page is a catalogue of possible notices and explicitly does not apply automatically to every work. | [Evidence 1](https://www.epa.gov/chemical-data-reporting/access-cdr-data); [Evidence 2](https://www.epa.gov/web-policies-and-procedures/epa-disclaimers) |
| ECHA CHEM REACH registered substances | B: original source for now | ECHA legal notice excludes third-party rights and whole/substantial databases from its general reuse permission. Generic acknowledgement is not sufficient evidence to mirror a bulk REACH/API cache; legal-notice text was retrieved through the official-domain search index after direct access returned 403. | [Evidence 1](https://echa.europa.eu/legal-notice); [Evidence 2](https://chem.echa.europa.eu/) |
| Nordic SPIN | B: original source for now | No reuse licence established; the original portal timed out in this review. Retrieval failure establishes neither prohibition nor permission. | [Evidence 1](http://www.spin2000.net/spinmyphp/) |
| Japan METI/NITE CSCL | B: original source for now | NITE general terms require attention to permission/quotation exceptions; J-CHECK also links a specific use concept. Do not apply one notice to every METI/NITE file. General website terms and the existing-chemicals-survey use concept may have different scopes. | [Evidence 1](https://www.nite.go.jp/en/homepage/index.html); [Evidence 2](https://www.nite.go.jp/chem/jcheck/top.action?request_locale=en); [Evidence 3](https://www.meti.go.jp/policy/chemical_management/english/files/concept_regarding_the_use_of_information.pdf) |
| Korea Chemical Statistics Survey | B: original source for now | Statistics interface accessible; no exact-data redistribution grant established. Public search access does not establish the terms for exported responses or derived project tables. | [Evidence 1](https://icis.mcee.go.kr/search/searchType6.do?pageType=tabC) |
| Canada CEPA Section 71 | A: public under conditions | Open Government Licence - Canada listed on official Section 71 dataset metadata. Conditional redistribution applies to information covered by the licence; third-party rights and other listed exemptions remain outside the grant. | [Evidence 1](https://open.canada.ca/data/en/dataset/22650b19-63b5-454f-8485-b6bd5e88e022); [Evidence 2](https://catalogue.ec.gc.ca/geonetwork/srv/api/records/c354599e-832c-4b86-a18a-b8b9a4a61931?language=eng); [Evidence 3](https://open.canada.ca/en/open-government-licence-canada) |
| South Korea MOEL new-chemical notices | B: original source for now | Notice attachments and a copyright-policy route located; attachment-specific reuse scope unconfirmed. The notice is mutable: currently linked attachments refer to September 2026, so the page URL alone is not a frozen version. | [Evidence 1](https://www.moel.go.kr/news/notice/noticeView.do?bbs_seq=20240100056); [Evidence 2](https://www.moel.go.kr/site/copyright/copyrightList.do) |
| Taiwan MOENV toxic chemicals | A: public under conditions | Open Government Data License, version 1.0, linked by TOXIC_P_19 and TOXIC_P_23. The two identified datasets allow redistribution/adaptation under their attribution terms; applicability to each local derived file requires a source mapping. | [Evidence 1](https://data.moenv.gov.tw/dataset/detail/TOXIC_P_19); [Evidence 2](https://data.moenv.gov.tw/dataset/detail/TOXIC_P_23); [Evidence 3](https://data.gov.tw/license) |
| Frozen exposure reference and provenance | C: confirmation required | Project-derived bundle; upstream distribution requirements unresolved. Project authorship of a derived table does not itself clear copied or transformed upstream evidence. | [Upstream register](data_access_register.json) |

## Acquisition and citation actions

These are source-specific recipes and unresolved steps, not a claim that every
reader can already retrieve the frozen collection. Preserve the exact filenames
and layout in [data preparation](data_preparation.md). Never change expected
policy hashes to accept a newer download.

### NORMAN SusDat

- **Acquire:** Obtain the specified export from NORMAN or its provider; the current page does not establish access to the frozen bytes.
- **Cite:** Cite NORMAN SusDat and contributing list identifiers; retain the declared 2025-06-03 export label as recorded, not an authenticated retrieval date.
- **Close before packaging:** Recover the exact export route and list-level notices; establish permission for mirrored aggregate records and analytical predictions.

### PubChemLite

- **Acquire:** Use the official site and Zenodo version history; do not replace PubChemLite.csv with the current download.
- **Cite:** Cite Schymanski et al. (2021), doi:10.1186/s13321-021-00489-0; identify the actual dataset version. Cite CCS work only when the matched input contains and uses that contribution.
- **Close before packaging:** Locate the historical release matching the local hash, retain attribution and licence notices, and document any transformation. The current candidate is not the frozen input.

### PlastChem

- **Acquire:** The version-specific official XLSX is accessible. It is a candidate source, not a byte-identical replacement for the frozen workbook.
- **Cite:** Cite Wagner et al., State of the science on plastic chemicals, dataset version 1.01, doi:10.5281/zenodo.15397723; preserve creator and licence notices.
- **Close before packaging:** Document the local workbook as a byte-different copy with scientifically equivalent tables, retain the comparison report and disclose known changes; assess the intended distribution against the NC scope.

### UNEP

- **Acquire:** Use the UNEP report/annex route or request the specific annex from the provider; do not treat the report PDF as the required input.
- **Cite:** Cite UNEP (2023), Chemicals in Plastics: A Technical Report, plus the exact annex identity when established.
- **Close before packaging:** Recover the official Excel annex and workbook correspondence; inspect annex-specific notices. Search-index evidence lists an Excel annex, but direct retrieval failed.

### MPLEACH

- **Acquire:** Obtain MPLEACH.xlsx from the version-specific record; keep the frozen local file unchanged for historical reproduction.
- **Cite:** Cite Alygizakis, Roosma, Brunner and Slobodnik, S133 MPLEACH, version NORMAN-SLE-S133.0.1.0, doi:10.5281/zenodo.18157912.
- **Close before packaging:** Attach the existing scientific-table equivalence result, preserve both hashes and indicate local changes without inventing editing history.

### FCCmigex

- **Acquire:** Use the official FCCmigex page to reach NORMAN S112/Zenodo. The candidate release is not yet validated as the frozen source.
- **Cite:** Cite Geueke et al., doi:10.1080/10408398.2022.2067828, the FCCmigex website and the actual S112 release DOI once matched.
- **Close before packaging:** Identify which S112 version produced FCCmigex.xlsx and compare the workbook before assigning a version. Preserve attribution and describe changes.

### FCChumon

- **Acquire:** Retrieve the Supplementary Tables through the original article/provider. Do not assume the dashboard export and supplement are interchangeable.
- **Cite:** Cite Geueke et al., Evidence for widespread human exposure to food contact chemicals, doi:10.1038/s41370-024-00718-2; online publication 2024, journal volume 35 (2025), 330-341.
- **Close before packaging:** Match the exact supplement and inspect credit lines before extending article-level permission to FCChumon.xlsx. Publisher search-index text was available; direct HTML redirected to an inaccessible authentication endpoint.

### FCCprio

- **Acquire:** Obtain FCCprio-List-v0-2-Zenodo-20260115.xlsx from the version 0.2 record, not the concept DOI current release.
- **Cite:** Cite Wiesinger et al., Food Contact Chemicals Priority (FCCprio) List, version 0.2, doi:10.5281/zenodo.17199870, and its accompanying methodology.
- **Close before packaging:** Use the version DOI in release citations; preserve the byte-difference/content-equivalence audit and a transparent local-copy notice.

### LitChemPlast

- **Acquire:** Use LitChemPlast_v20240809.xls from the versioned record; document the local filename LitChemPlast.xls.
- **Cite:** Cite Wiesinger et al., LitChemPlast database, v20240809, doi:10.5281/zenodo.13271346, and the associated article doi:10.1021/acs.estlett.4c00355.
- **Close before packaging:** Retain the official-to-local filename mapping, creator notices, both hashes and the existing content comparison. Do not invent a retrieval date.

### ICCA

- **Acquire:** Readers should obtain access through the provider registration route for now; a registration route does not guarantee retrieval of the frozen CSV.
- **Cite:** Cite ICCA Plastic Additives Database, the actual export/version and relevant upstream sources; snapshot date remains unrecorded.
- **Close before packaging:** Recover export/account terms, provenance and allowed reuse scope. No account was created, agreement accepted or provider contacted in this review.

### UCSF

- **Acquire:** The publisher supplement record identifies file eh5c00197_si_001.xlsx; obtain it through the official record without overwriting frozen inputs.
- **Cite:** Cite Yang et al., Unraveling Plastic-Related Chemical Exposures during Pregnancy and Their Associations with Pregnancy Outcomes Using Suspect Screening Analysis, doi:10.1021/envhealth.5c00197, and supplement doi:10.1021/envhealth.5c00197.s001.
- **Close before packaging:** Compare the local workbook with eh5c00197_si_001.xlsx in a separately approved content audit; preserve NC terms, attribution and change notices. A name match is insufficient.

### PlasticMAP

- **Acquire:** Obtain es1c00976_si_001.zip from the publisher supplement; identify the required workbook member before preparing an acquisition recipe.
- **Cite:** Cite Wiesinger, Wang and Hellweg, Deep Dive into Plastic Monomers, Additives, and Processing Aids, doi:10.1021/acs.est.1c00976, and supplement doi:10.1021/acs.est.1c00976.s001.
- **Close before packaging:** Inspect the official archive member and match PlasticMAP_S1_210611.xlsx; retain NC terms and any change notice. Do not compare a ZIP checksum directly with an extracted XLSX.

### Frozen VEGA reports

- **Acquire:** The exact 20 frozen reports must be supplied by their generating project or an authorised archive; downloading VEGA does not supply them.
- **Cite:** Cite VEGA and the actual model/QMRF references and versions listed in plastprior/qsar_models.json; record the application build and generation date if recovered.
- **Close before packaging:** Recover report-generation provenance and examine report/model notices. Distinguish project-generated numerical predictions from any copied reference material.

### GIC inventory

- **Acquire:** Obtain compiled inputs through their provider/project route only after upstream list decisions; the code repository is not an exact-data acquisition recipe.
- **Cite:** Cite GIC at revision 9487e9395ee51f7cce304ff65a041854d908211d and each used inventory/list provider and snapshot; distinguish current pinned code from the unrecorded historical version.
- **Close before packaging:** Map the used list tags to providers and terms, and recover metadata-table provenance. Retain identity/name/shared-identifier flags; do not treat software licensing as data clearance.

### Patent query evidence

- **Acquire:** Obtain the frozen query output from the generating project; live queries are not a reproducible replacement for the recorded snapshot.
- **Cite:** Cite NCBI PubChem patent resources, exact query parameters, retrieval timestamps, counting method, failure status and file hash.
- **Close before packaging:** Assess project-generated count/query records separately from third-party content; verify the retained fields and error text, then choose an appropriate project distribution notice. Preserve failed queries and valid zeros.

### Literature query evidence

- **Acquire:** Obtain the frozen query output from the generating project; live queries are not a reproducible replacement for the recorded snapshot.
- **Cite:** Cite NCBI PubMed literature resources, exact query parameters, retrieval timestamps, counting method, failure status and file hash.
- **Close before packaging:** Assess project-generated count/query records separately from third-party content; verify the retained fields and error text, then choose an appropriate project distribution notice. Preserve failed queries and valid zeros.

### US EPA Chemical Data Reporting

- **Acquire:** Use year-specific EPA public downloads and recorded ChemView routes; do not substitute the newest CDR cycle.
- **Cite:** Cite US EPA, the actual CDR/IUR reporting years, public release/version, dictionary and retrieval records; distinguish reporting years from download dates.
- **Close before packaging:** Match each required archive/response to the frozen source manifest and inspect its notices; keep derived summaries and raw-source attribution separate.

### ECHA CHEM REACH registered substances

- **Acquire:** Use the original ECHA service under its terms for now. Exact historical cache availability remains unestablished.
- **Cite:** Cite ECHA CHEM, query/retrieval date, relevant substance/list identifiers and notices; preserve limitations on tonnage interpretation.
- **Close before packaging:** Determine applicable database/API terms and scope of the collected cache before distribution. Review derived evidence separately; do not infer blanket permission from public browsing.

### Nordic SPIN

- **Acquire:** Use the original SPIN provider route for now; establish historical access or a permitted project mirror before claiming independent reproduction.
- **Cite:** Cite Nordic SPIN, contributing national registers, coverage years, query dates and source response hashes.
- **Close before packaging:** Recover applicable portal/national-register terms and a frozen access route; map the response audit to required derived tables.

### Japan METI/NITE CSCL

- **Acquire:** Use the original METI/J-CHECK sources for now rather than publishing a bulk response mirror.
- **Cite:** Cite the actual METI/NITE source, CSCL fiscal years, MITI/CAS mapping source and retrieval date; preserve unconfirmed identifier-linkage limitations.
- **Close before packaging:** Map each downloaded response to its provider and applicable notice. The linked concept document was identified but not reviewed here; obtain a scope-specific distribution decision.

### Korea Chemical Statistics Survey

- **Acquire:** Use the original statistics service for now; do not substitute national totals for missing compound-specific data.
- **Cite:** Cite the chemical statistics provider, survey years, query filters, units and retrieval evidence; distinguish aggregate data from compound-level observations.
- **Close before packaging:** Identify dataset/export terms and map the frozen demo/derived files to actual source responses. Retain evidence eligibility exclusions.

### Canada CEPA Section 71

- **Acquire:** Use the Section 71 catalogue and initiative-specific resources; public access to the latest files does not identify the frozen collection.
- **Cite:** Cite Environment and Climate Change Canada, the relevant Section 71 initiative and dataset identifier; include the required Open Government Licence attribution.
- **Close before packaging:** Map source_file_index.csv entries to specific public resources and notices, record release/hash correspondence, and label project transformations. Official-domain indexed metadata supplied the licence evidence after direct portal access failed.

### South Korea MOEL new-chemical notices

- **Acquire:** Acquire the specific notice attachments through MOEL for now; keep the project source manifest for historical file identity.
- **Cite:** Cite MOEL, notice identifier, exact attachment/version, coverage years and retrieval date.
- **Close before packaging:** Recover the frozen attachment IDs and any item-level public-use marker or applicable notice; do not assume an open licence from government ownership.

### Taiwan MOENV toxic chemicals

- **Acquire:** Use dataset-specific downloads/history through MOENV; preserve the exact historical response or a properly attributed frozen copy.
- **Cite:** Cite Ministry of Environment / Chemicals Administration, TOXIC_P_19 and TOXIC_P_23, dataset titles, snapshot dates and the required attribution statement.
- **Close before packaging:** Match downloaded response hashes and dataset IDs to download_audit.csv, retain notices and describe transformations. Current October 2026 data are not substitutes for the frozen snapshot.

### Frozen exposure reference and provenance

- **Acquire:** The generating project must supply the exact eight-file bundle through an approved route. It is not recreated by the current raw-data workflow.
- **Cite:** Cite the PlastPrior version, original transformation/run identifiers and each contributing source; preserve all eight manifest and reference file hashes.
- **Close before packaging:** Resolve upstream file scopes and define a minimal complete bundle. Review machine paths and operational metadata in manifests without altering the frozen originals.

## What can be released now, and what remains conditional

- This checklist, bibliographic references, source URLs, file hashes and original
  project-written methods can form the documentation portion of a release,
  subject to the separate project ownership/licensing decision. Source payloads
  are not embedded in this checklist.
- The named category A official deposits/datasets have a documented conditional
  sharing route. Retain their notices and verify the object being distributed.
  The safest immediate acquisition instruction is the official record, while
  local-copy correspondence is completed. This does not make those official
  objects drop-in substitutes for fingerprinted analysis inputs.
- Category B local collections should remain outside a project download for now.
  Provider acquisition is the current proposed route; it still needs a workable
  exact-snapshot recipe before independent reproduction can be claimed.
- Category C files require the specific decisions above. A generated numerical
  prediction or query count is not automatically restricted because its software
  or service has a licence; conversely, copied reference content is not cleared
  merely by being included in a project-generated file.

The four previously compared PlastChem, MPLEACH, FCCprio and LitChemPlast
workbooks have equivalent scientific tables but different bytes; retain their
[comparison report](workbook_comparison.md) and avoid claiming a known editing
history. New metadata checks found byte mismatches for UCSF, FCCmigex and the
current PubChemLite candidate, but **no new scientific-content comparisons were
performed**. PlasticMAP requires a ZIP-member comparison, not a ZIP/XLSX hash
comparison. No remote research-data files were downloaded in this review.

## Final results and the frozen reference bundle

The CSV and SQLite are not automatically cleared by excluding `data/` from Git.
The database retains source records, membership links, evidence bodies and
historical/analysis records. Compact storage changes representation, not the
underlying source material or its applicable terms. Scores and factual indicators
must be assessed separately from copied source text, structured source records,
third-party classifications and bulk database extracts.

Before distributing the full SQLite, map retained source-bearing artifacts and
fields to this register, resolve unresolved scopes and attach source-specific
attributions. Do not apply one unrestricted project licence to the entire
combined database by default. NC-licensed components, ECHA database exceptions
and GIC upstream lists deserve explicit review. This review does not decide
whether any particular numerical derivative inherits a source licence.

The eight-file `ExposureReference/20261006T233429Z/` bundle is required for the
current workflow but combines derived evidence and provenance from upstream
sources. Its release route cannot be settled independently of those sources.
Metadata preparation for publication should use a separate reviewed copy where
necessary; preserve the frozen original manifests and hashes. No local package,
result or raw response has been deleted, altered or uploaded in this review.

## Prioritised completion work

1. **Close the licensed-source correspondence gaps.** Start with the four
   already-compared workbooks: prepare honest local-copy/change notices and
   source-specific attributions. Then separately review the UCSF, PlasticMAP,
   FCCmigex and historical PubChemLite candidates. These comparisons may be
   read-only; adoption of replacement inputs is a different task.
2. **Resolve the highest-impact source scopes.** Review ECHA bulk/API use,
   ICCA export terms, METI/NITE source-specific notices, GIC contributing lists
   and the unresolved NORMAN/UNEP/SPIN/Korean sources. Use explicit existing terms
   where sufficient; ask providers only for unresolved questions. No outreach
   was sent as part of this review.
3. **Finish locally generated evidence provenance.** Identify VEGA application
   builds and report contents, and document query output attribution, timestamps,
   counting methods and error fields. Keep failed queries and valid zeros intact.
4. **Define the minimal exact-input package and result permissions.** Use the
   frozen manifests to identify necessary raw responses; do not assume all
   42,202 local data files are needed or that a raw-response cache is disposable.
   Separate permitted copies, provider-acquired inputs and unresolved artifacts.
5. **Test the acquisition recipe after decisions.** A separate reader must be
   able to obtain each required frozen object and pass hash checks. Only then
   bind the chosen inputs, source notices and final-result permissions to a
   versioned public package. No full reproduction was performed in this review.

## Acceptance checklist

- [x] Review all 25 source/bundle groups and record explicit dispositions.
- [x] Distinguish official licensing evidence from local snapshot readiness.
- [x] Supply source-specific acquisition leads, citation instructions and actions.
- [x] Retain historical byte/content comparisons without replacing inputs.
- [ ] Establish each required local-to-official mapping or transparent derivation.
- [ ] Complete attribution/change notices and unresolved content-specific terms.
- [ ] Resolve access to all required frozen files and the derived reference bundle.
- [ ] Complete source/field-level distribution review for the final CSV/SQLite.
- [ ] Demonstrate independent acquisition and reproduction from the release recipe.

A blocked request, public landing page or article citation does not settle
redistribution. Unknown historical information remains unknown. The existing
scientific validation, identity quarantine, GIC flags, missingness and scoring
rules are unchanged.

## Integrity checks for this review

All 42,202 original data files match their preserved SHA-256 fingerprints.
All 54 tracked implementation, policy, test, dependency and Notebook files
match the committed baseline. The retained final CSV and SQLite hashes are
unchanged. The previous register content is preserved, all 25 new decisions
have acquisition/citation/action fields, and local document links resolve.
These checks do not rerun scoring or establish new scientific equivalence.
