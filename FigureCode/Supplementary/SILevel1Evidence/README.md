# Level 1 supplementary evidence

Code lives here. Data live in `result/figure_data/SILevel1Evidence/`; the current
workbook, PDF and preview are flat in `result/figures/`.

```sh
.venv/bin/python FigureCode/prepare_data.py --figures SILevel1Evidence
.venv/bin/python FigureCode/Supplementary/SILevel1Evidence/run_plot.py
.venv/bin/python FigureCode/Supplementary/SILevel1Evidence/run_plot.py --verify
```

Preparation reads the pinned current result, five-level policy and primary-use
annotations. Rendering uses the existing `si_payload.json`; it does not prepare
data or recalculate scores. The complete 101-row workbook/PDF remains available
separately from the manuscript-only PPT. A successful render marks it for review.
