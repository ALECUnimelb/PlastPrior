# Manuscript figures

Use [INDEX.md](INDEX.md) and [SI_INDEX.md](SI_INDEX.md) for the current figure
selection and review status. Images and the SI workbook are flat in
`../result/figures/`. Tables are in `../result/figure_data/<figure>/`; manifests
are in `../result/figure_data/_metadata/<figure>/`.

Each figure has one current set. A successful build replaces that set after
validation and marks it for review. Approval changes metadata only; it does not
create or move a second file set. Failed builds preserve the last complete set.

```sh
.venv/bin/python Figure/Fig1/run_plot.py
.venv/bin/python Figure/SILevel1Evidence/run_plot.py
.venv/bin/python Figure/verify_figures.py
node Figure/update_ppt.mjs
```

The PPT command replaces the sole PPTX in `../result/`, preserving a manual
rename. If none exists, it uses `Figures.pptx`; multiple PPTs cause an error. It contains exactly nine slides: Fig. 1–5 and Extended Data Fig. 1–4.
Do not append standalone Fig. 3b, SI evidence pages, the identity list, the
classification tree or the old sensitivity figure. These are separate assets,
not presentation slides. Do not overwrite manual PPT edits unless regeneration
is requested.
No previous PPT is needed. `--review` remains an alias for the same command.

Fig. 3 retains its present five-level data and a/b/c+d layout; its visual redesign
is a separate task. Fig. 4 is the exact accepted three-panel composition export.
Fig. 5 and Extended Data Figs. 3–4 remain marked legacy pending further work.
Five-level classifications are figure labels only; CSV/SQLite scores, ranks and
Top-N membership are unchanged by plotting or storage operations.

The identity list and classification tree can be refreshed through
`.venv/bin/python Figure/run_retained.py Level1Identity` or `Level1IdentityTree`.
Their existing classified table is a fixed input; classification changes require
separate review. Retired experiment entrypoints stop before writing outputs.
Original scientific source code and research annotations remain available.

`figure_sources.json` pins the legacy evidence dependency under
`../result/figure_data/_dependencies/baseline/`. `managed_sources.json` pins the
current database/CSV. Historical manifests resolve through `_shared/result_paths.py`.
The existing sensitivity recovery archive is preserved. Do not substitute current
scenario views for the original baseline schema. See [storage rules](../docs/results_layout.md).
