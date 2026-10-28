# Figure code

`FigureCode/` contains implementations and configuration only. Current plotting
inputs live in `result/figure_data/<figure>/`, and finished images live directly
in `result/figures/`. Existing files are replaced; no dated or parallel copies
are created. Use [INDEX.md](INDEX.md) and [SI_INDEX.md](SI_INDEX.md) for figure status.

- `Fig1`–`Fig5`, `ExtendedDataFig1`–`ExtendedDataFig4`: manuscript figures.
- `Supplementary/`: SI evidence workbook/PDF, retained identity list and tree.
- `_shared/`: common plotting and storage helpers; `sensitivity/` contains the
  frozen sensitivity functions required by Extended Data Fig. 3.

## Prepare data, then render

```sh
# Refresh all current-dataset figure inputs together; no images or scores change.
.venv/bin/python FigureCode/prepare_data.py
# Validate preparation against existing tables without replacing anything.
.venv/bin/python FigureCode/prepare_data.py --check
# Render a layout from its prepared inputs.
.venv/bin/python FigureCode/Fig3/run_plot.py
.venv/bin/python FigureCode/Fig4/run_plot.py
.venv/bin/python FigureCode/Supplementary/SILevel1Evidence/run_plot.py
# Verify all current deliverables and original provenance.
.venv/bin/python FigureCode/verify_figures.py
```

Each R module has `prepare.R` for numerical input preparation and `build.R` for
rendering. CSV/JSON tables remain inspectable; `plot_data.rds` preserves the typed
R objects needed to render without reopening the analysis database. Its hash and
source lock are recorded in `figure_data/_metadata/<figure>/preparation.json`.
Layout work runs only the render command. Preparation stages the complete selected
set, validates it, and replaces it together. Changed numerical data mark the
existing images stale; verification and PPT generation reject stale figures until
they are rendered again. Failures retain the last complete set.

Fig. 5 and Extended Data Fig. 3 retain their fixed legacy baseline. Preparing them
requires explicit `--figures Fig5 ExtendedDataFig3`; this never upgrades their
scientific status. Extended Data Fig. 4 is a separate Dashboard capture. The
retained identity list and tree use their existing classified table through
`FigureCode/run_retained.py`. Structural reclassification requires separate
review, and a changed Level 1 membership fails the Fig. 4 consistency check.
Primary-use annotations are in `result/figure_data/_dependencies/`.

Changing the analysis dataset remains a coordinated data-update operation. Its
source locks and all dependent tables must be updated together before installation;
the database exporter rejects an uncoordinated replacement. Figure preparation
does not calculate scores, ranks or Top-N membership.

## Presentation

`node FigureCode/update_ppt.mjs` replaces the sole PPTX in `result/`, preserving
its manual filename. It defaults to `Figures.pptx` only when no PPTX exists and
rejects multiple decks. It includes exactly nine slides: Fig. 1–5 and Extended
Data Fig. 1–4. Standalone Fig. 3b, SI pages, identity/tree and old sensitivity
images are not appended. Do not run it over manual PPT edits unless regeneration
is requested. Fig. 3 no longer exports a standalone Fig. 3b on rebuild.

Current images and the user-edited presentation were preserved during the code
reorganization. Fig. 4 retains the accepted three-bar layout; Fig. 3 visual redesign
is a separate task. Original manifests retain historical paths, resolved through
`_shared/result_paths.py`. See [storage rules](../docs/results_layout.md).
