# Level 1 supplementary evidence module

This SI module makes the complete figure-defined Level 1 cohort inspectable by
compound, use, existing domain scores, unweighted components and GIC annotation.
It preserves the accepted evidence-grid grouping and palette. It is an evidence
table, not a new ranking or a statistical analysis. All records meeting the
five-level policy are included; 101 is the current result, not a selection limit.

Use [the SI index](../SI_INDEX.md) to choose the current files. The existing
`Level1Evidence` exploratory overview, accepted Fig. 4, other figures, formal
data and Dashboard are inputs or separate work; this module never rebuilds them.

## Deliverables and lifecycle

- `../../result/figures/Supplementary_Table_Level1.xlsx`: native, filterable Excel cells.
  `Level1 evidence` contains the complete table, with the first 19 columns
  matching the figure layout and audit fields to their right. `Definitions`
  describes columns, weights, colour codes, classification and source hashes.
- `../../result/figures/SILevel1Evidence.pdf`: complete, selectable-text SI figure, automatically
  paginated with repeated headings. The current cohort fits on three pages.
- `../../result/figures/SILevel1Evidence.png`: one preview of the opening Excel rows.
- `../../result/figure_data/_metadata/SILevel1Evidence/manifest.json`: source/code/output hashes and validation results.
- `../../result/figure_data/SILevel1Evidence/`: the single paired numerical
  snapshot (`compound_evidence.csv`, renderer payload and annotation-change log).
  These are SI source tables, not replacements for the formal results CSV.

Each successful build replaces the single current image/table set after validation.
Approval changes status only; it never creates a second copy. The manifest is in
`result/figure_data/_metadata/SILevel1Evidence/`. No dated versions or separate page
PDFs are retained. Temporary previews are removed.

```sh
cd /Users/ruiwang/Projects/APPs/PlastPrior
.venv/bin/python -B Figure/SILevel1Evidence/run_plot.py
.venv/bin/python -B Figure/SILevel1Evidence/run_plot.py --verify
```

After the user accepts the review, promote it without rerendering:

```sh
.venv/bin/python -B Figure/manage.py approve SILevel1Evidence
```

The build uses Python for source preparation, R (`grid`, `jsonlite`, `ragg`, `svglite`) for
the figure, and `@oai/artifact-tool` for native Excel. It requires `pypdf` for PDF
checks. The default Node and package paths are the bundled Codex runtime;
`PLASTPRIOR_ARTIFACT_NODE` and `PLASTPRIOR_ARTIFACT_MODULES` can select another
installation of that same workbook runtime. R drawing remains R-only.

## Updating after a new database run

Generate the new published run with the project's existing database workflow
first. Then explicitly select its directory, containing the results CSV,
`figure_data/_metadata/scenario_manifest.json` and `figure_data/_metadata/scoring_config.json`:

```sh
.venv/bin/python -B Figure/SILevel1Evidence/run_plot.py \
  --run-dir output/NEW_RUN \
  --annotations path/to/reviewed_use_annotations.csv
```

The default source is pinned in `source.json`. Explicit overrides never modify
that source or its annotations. The selected CSV hash and scoring configuration
must match its run manifest. Weight headers come from that run's configuration.
If domain thresholds change, also supply an explicitly reviewed compatible
five-level policy via `--policy`; incompatible rules fail instead of silently
reclassifying against old cutpoints. Update `source.json` through a reviewed code
change when the new run should become the default.

Annotations join on full `inchikey` and accept `record_id`, `Name`, `CAS`,
`primary_use`, `detailed_uses`, plus optional `source` (or `citation`) and
`review_status`. Duplicate or empty keys fail. New members without annotations
remain visible as `Unclassified / pending review`. Changed source names/CAS are
flagged; the current source identity is retained. The change log lists missing
annotations, annotations outside the cohort and membership changes relative to
the official snapshot (or previous review if none is official).

## Scientific contract and checks

- Apply the shared five-level matrix to the existing integer H/E scores.
  Current Level 1 means both H and E are 12–16 (vH). The source CSV's four-level
  classification remains separately visible as `Source level`.
- Copy H, E, total, competition rank and raw totals exactly. Reconcile against
  source weights and half-up rounding, but never replace them with recalculated
  scores. Ties remain ties; sorting is total descending, then InChIKey.
- Keep missing component cells blank and grey in Excel (`NA` in the figure).
  Preserve numeric zero and fractional values, including 0.25 and 0.5. Colours
  encode unweighted component score, not weighted contribution.
- Display IDs are row numbers, not ranks or durable chemical keys. InChIKey
  supports future joins; original annotation IDs are retained separately.
- GIC annotations are copied from the selected database, with code definitions.
  Unknown categories fail for review; they are never silently assigned a code.
- Supplied uses remain annotations. Missing row-level references are shown as
  blank, with review status recorded; the module does not invent citations.
- Dynamic pagination handles longer names and cohorts other than 101. No record
  is omitted to fit a page. Future empty cohorts fail and preserve the review.
- Verify every exported Excel value and text identifier, freeze panes, filters,
  conditional formatting, PDF page membership and all compound names. Source
  hashes are checked before and after generation. Temporary renders are deleted.

```sh
.venv/bin/python -B Figure/verify_figures.py
.venv/bin/python -B -m unittest discover -s Figure/tests -p 'test_si_level1.py' -v
```

## Draft SI caption

**Compound-level evidence for the highest-priority group.** All compounds with
very high hazard and very high exposure under the five-level figure policy are
listed in descending existing priority score, with InChIKey breaking display
ties. H and E are the separately rounded domain scores; Total and Rank retain
the published score and all-compound competition rank. Component tiles show
unweighted scores, with the applied weights above each column. Missing evidence
is distinguished from recorded zero. Primary uses are supplied annotations; GIC
codes describe the source database's regulatory annotations. Full definitions,
raw domain totals, identifiers and annotation provenance accompany the Excel
table. Current source: run `20261027T080120Z-rounded`, 101 compounds.
