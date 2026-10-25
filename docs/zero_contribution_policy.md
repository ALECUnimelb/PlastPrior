# Missing-evidence contribution policy

The current policy is `priority-zero-contribution-v1`. This supersedes the
complete-domain ranking gate recorded in earlier verification reports.

Raw unavailable P/B/M/T and exposure component scores remain null, with their
availability flags, reasons and source provenance. At aggregation only, a missing
component contributes zero. No available score is rescaled. Thus
`H = 2P + 2B + M + 3T`, `E` is the sum of six indicators in five dimensions,
and `S = H + E`. The two food-contact/biomonitoring indicators remain independently
additive even if one is missing. A joint dimension is complete only when both
are available.

A compound with any available component, including an evidence-supported zero,
is rankable. Only a record with all ten components unavailable receives `No data`
and no priority score/rank. H and E remain numeric contribution sums, including
zero for an entirely unavailable domain; domain status distinguishes this from
observed zero. Partial evidence does not withhold the other domain or total.

The dual gates are unchanged: High requires S >= 12, H >= 4 and E >= 4;
otherwise Moderate requires S >= 6, H >= 2 and E >= 2; otherwise Low.
Competition ranks use unrounded scores. Top-N includes all ties at the Nth
record, and reports requested N, actual size, cutoff and boundary group size.

`Priority_missing_reasons` explains component gaps independently of eligibility.
`Priority_ineligibility_reasons` applies only to entirely unavailable records.
Completeness is descriptive, not a ranking gate. Both the CSV and browser-detail
database identify the scoring policy; the browser also checks the CSV SHA-256.

## Evidence admission retained

The migration keeps upstream source admission unchanged. Fifteen unresolved
model-identity associations retain their QSAR/Pov/LRTP exclusions, while usable
structural, curated and exposure evidence still contributes. Name-only GIC
matches remain visible as review context but do not supply inventory points.
Shared identifiers require direct local tag support. Negative quantities,
lookup failures, ambiguous CAS links and unsupported market-presence assertions
are not restored as measurements or observed zeros. Any later restoration must
identify the source record and sufficient independent support, then rerun scores.

## Figures and sensitivity

Coverage uses raw availability, including supported zero. Positive-contribution
patterns and sensitivity use the full rankable population and zero numerical
contribution for missing inputs, while exporting original missingness. BCF
agreement compares selected QSAR BCF with curated B only; the structural rule
still participates in final B scoring. ADI sensitivity reruns canonical PBMT
selection at 0.50, 0.65, 0.80 and 0.85 with fixed exposure and LRTP inputs;
0.50 must exactly reproduce raw PBMT values/missingness and H/S/tiers.

## Verification

`tests/test_zero_contribution.py` exhaustively checks all 1,024 patterns of
availability across ten components. `scripts/audit_zero_contribution.py` uses
independent literal weights and thresholds, checks every compound and tie, and
compares evidence and source memberships with the pre-repair archive.
`scripts/adi_sensitivity.py` writes replacement Tables S8–S10 and compound-level
scenario outputs. Current verified population/counts are recorded in the
migration report, not inferred from historical verification numbers.

The repair is staged in a separate local worktree and candidate output. Previous
exports and historical reproductions remain available for audit. No online
publication is implied by creating the candidate.
