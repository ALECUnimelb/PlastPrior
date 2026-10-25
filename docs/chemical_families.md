# Structural chemical-family annotations

The final exporter applies `chemical_family_smarts_v2.0.0`, migrated from the previous
ChemicalPrio classifier. Classification uses the current `smiles_isomeric`, RDKit parent
normalization and explicit structural rules. All organic fragments are considered;
multiple family memberships are permitted. Original identities, source memberships,
scores, completeness, eligibility, competition ranks and Top-N membership are unchanged.

The CSV contains one additional column, `category_labels`, with semicolon-separated labels.
SQLite `chemical_family_audit` records the original and classification-parent structures,
status, matched rules, warnings, salt/parent-change flags and rule version. Metadata records
RDKit and rule versions and coverage. Empty labels distinguish no assignment only through
the audit status (unclassified, missing, invalid or normalization error); they do not prove
absence of all chemical families. These nine families are not an exhaustive taxonomy.

Rules preserve the established implementation: PBDE/PBB/PCB require the specified ether
or biphenyl core, exact carbon/oxygen counts and the designated halogen, excluding other
heavy atoms. Dioxin/furan families require at least two corresponding halogens; mixed
chlorinated/brominated structures and mono-halogenated cases are flagged, not forced into
pure polyhalogenated families. OPE requires a phosphate ester and excludes direct P–C
bonding. PFAS uses the classifier's fully fluorinated CF2/CF3 criterion. Exact rule
expressions are preserved with the software and in metadata; this is a screening annotation,
not an independent validation of every family definition.

The Dashboard groups labelled records with an empty search; searching an exact family name displays
only its members, excluding accidental name or identifier substrings. Overlap is preserved, so group-member totals may exceed unique compounds.
The Max badge means the highest eligible member priority, not a score for the family.
An entirely unranked family shows a dash. Clicking a member uses its full InChIKey.
