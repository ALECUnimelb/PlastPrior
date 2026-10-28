# Current result storage

`result/` is the only persistent generated-result location. Its public entries are:

- `PlastPrior_results.csv`
- `PlastPrior_results.sqlite`
- `PlastPrior_dashboard.sqlite`
- `figure_data/`: one numerical input set per figure
- `figures/`: flat PNG/PDF images and current SI workbook
- `Figures.pptx` by default: the single review presentation, replaced on update.
  A user-renamed sole PPTX keeps its name; the generator does not add another.

`figure_data/_metadata/` holds scoring configuration, source/build records and
validation. Its `manifest.json` records verified relocation mappings without
rewriting original provenance. `figure_data/_dependencies/` holds the immutable
baseline still needed by frozen figures/scenario export and the classification
handoff awaiting a return. These are research dependencies, not alternative
current result sets. Do not delete them until their consumers no longer need them.

Each figure has one current image/data set. `FigureCode/catalog.json`, `INDEX.md` and
`SI_INDEX.md` record approval, pending review or legacy status. Rebuilding replaces
the same files and marks review; acceptance changes status without making a second
copy. Retained identity-list, tree and sensitivity images are explicit exceptions
to manuscript-only selection. Other exploratory outputs are retired.

Build in temporary staging, validate, then replace the complete set with rollback.
Figure publication swaps a staged result tree so images and tables stay paired.
Unchanged files may be hard-linked into temporary staging; never edit those links
in place. New files must replace links. Stop readers during the replacement window.
Data refresh with existing figures is blocked until dependent data are refreshed
together. Layout/storage maintenance must not recalculate scores or ranks.

Run `.venv/bin/python FigureCode/verify_figures.py` for scientific/provenance checks,
and `node FigureCode/update_ppt.mjs` for the fixed presentation. It uses current
catalog status and never auto-approves a figure. The deck contains only Fig. 1–5
and Extended Data Fig. 1–4 (nine slides). Standalone Fig. 3b, SI evidence pages,
identity/tree figures and old sensitivity plots are excluded from the deck.
Temporary QA renders are removed.
No `output/`, `results`, dated result directories or extra PPTs are created.
Generated results and the local AGENTS.md agreement remain excluded from Git.

Plotting implementations are in `FigureCode/`; retained supplementary modules are
in `FigureCode/Supplementary/`. Numerical preparation is explicit through
`FigureCode/prepare_data.py`. It stages and replaces the selected input set together;
render commands consume that prepared set. The R payload is kept with its CSV
tables, with provenance in `_metadata/<figure>/preparation.json`. Changed inputs
mark existing images stale until rebuilt. Layout-only work does not run preparation.
