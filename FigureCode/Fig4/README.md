# Fig. 4 — Level 1 composition

`prepare.R` checks the same 101 Level 1 compounds, retained primary-use and
structural assignments, and GIC annotations. `build.R` renders the accepted
three-panel composition from `result/figure_data/Fig4/`.

```sh
.venv/bin/python FigureCode/prepare_data.py --figures Fig4
.venv/bin/python FigureCode/Fig4/run_plot.py
```

The current PNG/PDF remain byte-identical to the accepted export. `verify.py`
checks that original snapshot; `approved_composition.json` is its source lock.
Historical sensitivity functions live in `_shared/sensitivity/`, consumed by
Extended Data Fig. 3. The retained sensitivity image and original research
archive remain unchanged.
