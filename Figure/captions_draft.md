# Figure caption drafts

For author review. These captions accompany the revised figures; the manuscript has not been modified. Scientific definitions and cautions are retained from the existing captions.

## Fig. 2

Fig. 2 | PBMT score coverage and concordance with PlastChem. (a) Availability of accepted computational and mapped PlastChem scores among 15,125 compounds. Bars partition the full inventory into four mutually exclusive categories: computational only, shared, PlastChem only and neither. (b–e) Paired score comparisons for toxicity, bioaccumulation, mobility and persistence, with shared n = 2,963, 270, 135 and 234, respectively. Bars above the matrices show exact agreement, nonzero |Δ| ≤0.5, 0.5<|Δ|≤1 and |Δ|>1, from left to right. Numerical labels are shown only for counts of at least 2 and at least 2.5% of the largest cell count within each matrix; unlabelled cells may therefore contain nonzero counts. Outlines mark exact score agreement. Shading represents within-domain fractions, scaled separately for each domain. Mean |Δ| is the mean absolute ordinal-score difference. Bioaccumulation uses selected QSAR BCF evidence and excludes the structural halogen rule. Missing scores are excluded from paired comparisons; supported zeros remain valid. These descriptive comparisons do not establish predictive accuracy.

## Fig. 4

Fig. 4 | Sensitivity of rankings and priority tiers. (a) One weighted input is removed at a time from its domain and total, without rescaling. High retention is the fraction of 3,144 baseline High compounds still meeting the dual gates; rank correlation is Spearman ρ for total scores. (b) Baseline and six alternative scenarios compare rank correlation, overall tier agreement and High-set Jaccard similarity. Equal PBMT weights are all 2; other scenarios alter inventory scoring, cap exposure at 8, or shift the High total threshold to 11 or 13. Domain gates remain fixed. These are deterministic stress tests, not uncertainty intervals.

## Fig. 5

Fig. 5 | Policy concordance and stable candidates. (a) Prevalence of strong-action status by priority category, with Wilson 95% confidence intervals; the high-versus-low odds ratio is 4.23 (Wald 95% confidence interval, 3.72–4.82). (b) Capture of strong-action compounds at a common 20.8% screening fraction, interpolating between tied-score groups; the dashed line marks random expectation. (c) Regulatory context of 1,615 stable high-priority candidates outside strong-action categories. Stability requires baseline total ≥13 and totals ≥12 under four alternative scoring schemes, with H and E each ≥4 throughout. (d) NORMAN SusDat annotation among the 31 candidates without a matched GIC listing: 30 have no SusDat match and one matches without a resolved platform prediction. Absolute counts are shown at each step. The final platform count is conditional on that single match. Concordance is not independent validation, and absent annotation does not establish analytical impossibility.

## Extended Data Fig. 2

Extended Data Fig. 2 | PBMT availability and positive exposure-evidence patterns. (a) Exact combinations of nonmissing final PBMT scores, including evidence-supported zeros. Of 15,125 compounds, 8,550 have all four domains and 2,087 have none. (b) Exact combinations of positive scores across five exposure dimensions; 14,073 compounds have at least one positive available contribution and 1,052 have none. Missing components contribute zero only to sums; raw availability remains separate. Food-contact and human-biomonitoring evidence form one dimension. Complete source tables retain all 16 hazard and 32 exposure patterns, including zero-count combinations. The panels use distinct membership definitions and do not both measure missingness.

## Extended Data Fig. 3

Extended Data Fig. 3 | Positive-scoring input breadth and prevalence. (a) Within-tier distribution of the number of positive weighted inputs among four PBMT domains and six exposure indicators. (b) Within-tier prevalence of a positive contribution from each input. The median positive-input counts are 3, 5 and 7 for Low, Moderate and High priority, respectively. Positive-input breadth differs from evidence completeness because a scoreable zero is not a positive input. The patterns are descriptive because the same inputs determine the tiers.

## Fig. 1

Fig. 1 | Database assembly and use. Source records are resolved to compound identities, linked to hazard and exposure evidence, and delivered through a database and dashboard. Compounds unsuitable for QSAR remain in the inventory. Missing components contribute zero only when summing scores, and their unavailable status is retained. Partial evidence does not preclude ranking; all 15,125 compounds in this run have at least one available component. Regulatory action and analytical-platform annotations provide context and do not contribute points.

## Fig. 3

Fig. 3 | Priority landscape and component evidence profiles among 15,125 compounds. (a) Total-score distribution in one-point intervals, colored by priority category; labels show bin totals. The inset shows priority categories and their regulatory context. (b) Hazard–exposure combinations, with circle area representing compound count. High requires S ≥12 and H and E each ≥4; otherwise Moderate requires S ≥6 and both components ≥2. Remaining records with evidence are Low. (c) Mean hazard and exposure contributions within the same intervals. (d) PBMT profiles distinguish missing evidence from supported zero and retain curated scores of 0.25. (e) Five exposure-dimension profiles; food contact and biomonitoring form one joint dimension. The Partial evidence category identifies a joint dimension with only one available indicator; its available contribution is retained in E. A numerical zero contribution does not establish absence of hazard or exposure.

## Extended Data Fig. 4

Extended Data Fig. 4 | Compound-level review illustrated with decabromodiphenyl oxide in the current local production build. The overview links chemical identity to hazard components, exposure proxies and total score. The final B score includes the structural halogen rule, while the displayed QSAR logBCF remains separate. The acute fish endpoint is LC50. Regulatory status and predicted analytical platform contribute no points. The sidebar count includes collapsed chemical-family groups and is not the compound total. The screenshot is unedited; source hashes and capture conditions are retained.
