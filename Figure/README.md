# Manuscript figures

Use [INDEX.md](INDEX.md) to select files. It distinguishes approved current figures, pending reviews and frozen figures. `catalog.json` is the machine-readable status record; rebuild the index with `.venv/bin/python Figure/manage.py index`.

## One official version and one review

- Official images: `<figure>/output/`. Replace only after the user accepts the pending figure.
- Pending images: `<figure>/review/`. Every successful rebuild replaces this one pending version.
- Numerical tables: `../output/figure_data/<figure>/output/` or `review/`, paired to the corresponding images.
- Default deliverables: PNG (600 dpi), editable PDF and one `manifest.json`. Fig. 3b also has standalone PNG/PDF exports. Temporary build files are removed on success or failure; a failed replacement restores the previous image/table pair.
- The manifest contains exact source, code, table and image hashes, caption facts and any build-specific checks. Do not rename, mix or edit the derived tables independently.
- Do not create `_v2`, `_final`, timestamped previews or copied plotting scripts. Git retains source history; dated scientific input runs remain immutable audit records, not competing current figures.
- The 101-compound classification handoff under `../output/2026-10-28/level1_classification_handoff/` is research input awaiting a return, and is retained.

Running a managed figure builds **review only**:

```sh
.venv/bin/python Figure/Fig1/run_plot.py
.venv/bin/python Figure/Fig2/run_plot.py
.venv/bin/python Figure/Fig3/run_plot.py
.venv/bin/python Figure/ExtendedDataFig1/run_plot.py
.venv/bin/python Figure/ExtendedDataFig2/run_plot.py
```

After the user explicitly accepts a particular review, promote that exact output (example):

```sh
.venv/bin/python Figure/manage.py approve Fig1
```

Promotion verifies the reviewed code, inputs and output hashes, replaces the official image/table pair and removes the pending pair. It does not rerender the approved image. Do not promote all figures automatically.

## Scientific sources and scope

The managed figures read `output/2026-10-27/PlastPrior_results.csv` and the read-only `current_compounds`/`scenario_results` views in the matching full SQLite. `managed_sources.json` pins these files. Scores, ranks, Top-N membership and raw evidence are never recalculated by figure maintenance.

`_shared/five_level_policy.json` defines the **figure-only** five-level matrix and approved palette. H and E use the existing separately rounded integers. Domain labels are L = 0–3, M = 4–7, H = 8–11, vH = 12–16. Level 1 requires vH/vH (101 compounds); Level 2 requires vH/H in either order (1,119); Level 3 contains the remaining vH pairs and H/H (3,482); Level 4 contains other pairs with at least one H (4,702); Level 5 contains the remainder (5,721). Counts sum to 15,125.

Formal CSV/SQLite and Dashboard still carry their existing four-level classification. Figure labels do not overwrite them. Fig. 1 makes this figure scope explicit. Fig. 2 and Extended Data Figs. 1–2 concern raw evidence/provenance and retain their original membership definitions; their numerical tables are checked against the frozen baseline.

The approved Fig. 3 uses a/b/c+d rows at 183 × 218 mm, plus a standalone 260 × 110 mm matrix. Five solid colors indicate levels, all 289 integer H/E cells show counts, and dashed boundaries mark the 4 × 4 label regions. Color intensity does not encode count. Raw component profiles distinguish missing evidence, supported zero and fractional scores. The axis guides use the four domain-label colors.

## Deferred figures and historical records

Fig. 4, Fig. 5 and Extended Data Fig. 3 remain frozen pending redesign. Extended Data Fig. 4 also remains frozen because Dashboard has not been migrated. Do not run their legacy builders as part of this update.

`figure_sources.json` and `../output/2026-10-26/figure_data/` retain the old manuscript baseline. Historical formal images for figures awaiting review remain in their existing `output/` directories, clearly marked in INDEX.md. Old baseline verification scripts and policy tests serve historical reproduction; they are not the current mixed-status verification entry point.

Existing PPTX decks are historical. No new deck is produced in this update. `update_ppt.mjs` refuses to assemble a deck while any figure is deferred or awaiting approval, preventing accidental mixing of policies. Future deck revision is a separate operation.

## Verification

Run from `/Users/ruiwang/Projects/APPs/PlastPrior`:

```sh
.venv/bin/python Figure/verify_figures.py
.venv/bin/python -m unittest discover -s Figure/tests -p 'test_*.py' -v
```

Verification reads hashes and scientific tables without modifying them. It checks all 289 classification combinations, all 15,125 rounded scores, the five level totals, current manifests and preserved legacy outputs. Extended Data Fig. 1 also runs its exact SVG alignment audit during generation; that temporary SVG is deleted after the audit and the result is stored in the manifest. `audit_archive/figure_maintenance/receipt.json` records this maintenance operation and protected-file checks.

All quantitative drawing uses R. Captions are maintained in [captions_draft.md](captions_draft.md). The canonical repository root is `/Users/ruiwang/Projects/APPs/PlastPrior`; the retired worktree is recovery material only.
