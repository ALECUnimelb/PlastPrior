# Current PlastPrior figures

Nine figures, one folder per figure. Their input files are locked by SHA-256 in `figure_sources.json`; changing a file or scoring policy stops the build. Current run: `20261025T084218Z-16d2169b`. Inputs are referenced in `audit_archive/`, never copied into individual figure folders.

- `Fig1`–`Fig5`, `ExtendedDataFig1`–`ExtendedDataFig4`: `run_plot.py`, R drawing code (or real dashboard capture), and generated `output/`.
- `output/`: final figure, `source_data/`, caption facts and a provenance manifest with source, code and output hashes.
- `_shared/`: read-only source access, shared plotting style and scenario definitions.
- `captions_draft.md`: revised caption draft; also embedded in PPT speaker notes.
- `verify_figures.py`: independent source-value, missingness, denominator, sensitivity, capture and alignment checks; writes `verification.json`.
- `update_ppt.mjs`: updates the nine-slide review deck from verified PNG outputs.
- `.history/`: ignored local originals and obsolete reproduction paths, retained for recovery. Active builds do not read this directory.

## Rebuild one figure

Run from the repository root, for example:

```sh
.venv/bin/python Figure/Fig2/run_plot.py
```

Use the same command for each other figure. R dependencies include ggplot2, patchwork, DBI, RSQLite, jsonlite, readr, ragg, svglite, scales, dplyr and ggVennDiagram. Python uses the project environment. Statistical figures export SVG/PDF and 600-dpi PNG/TIFF; the dashboard figure remains a genuine raster screenshot.

Extended Data Fig. 4 additionally needs the sibling `ChemicalPrioDashboard/app` dev server on `http://127.0.0.1:5198/` (override with `--dashboard-url`), Chrome and Playwright available to Node. Set `NODE_PATH` to an installed Node module directory when needed. The capture waits for the paired audit evidence, not just the CSV summary. Dashboard source revision and file hashes are recorded with the screenshot.

```sh
.venv/bin/python Figure/verify_figures.py
node Figure/update_ppt.mjs
```

The PPT builder requires `@oai/artifact-tool`, the presentations skill finalizer and its bundled Python runtime. Their paths can be supplied through `NODE_PATH`, `PRESENTATIONS_SKILL_DIR` and `PRESENTATIONS_PYTHON`; defaults match this workstation. It preserves the existing deck's layout, embeds the current figures without cropping, and adds captions and provenance to notes. Build previews and receipts stay in `.history/`.

## Population and missing-data rules

The full inventory contains 15,125 compounds. Formal ranking includes 4,244 (365 low, 1,828 moderate, 2,051 high); 10,881 remain insufficient evidence. Total-score, sensitivity and GIC comparisons use the fixed ranked cohort. Full-inventory coverage plots retain unavailable evidence explicitly. Exposure-pattern overlap uses 7,951 complete-exposure compounds and separately reports 7,174 excluded compounds. Missing numeric scores are never filled with zero. Deliberately removing an observed input in a sensitivity scenario is recorded as a perturbation.

Fig. 5 does **not** support the old claim of monotonic strong-action enrichment: high/moderate/low proportions are 17.9%/6.9%/15.6%. The new captions state the denominators and limits. Verification establishes correspondence to the locked PlastPrior analysis; it does not rerun external QSAR tools or validate the correctness of external database records.

`Final_Figures.pptx`, generated figures/tables, verification output, temporary PowerPoint lock files and `.history/` are ignored by Git. The manuscript is not automatically edited.
