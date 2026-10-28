# Fig. 4 — Level 1 composition

The approved figure is the three-panel R composition figure: primary uses,
structural classes and GIC regulatory annotations, each covering 101 compounds.
Use `../../result/figures/Fig4.png` and `Fig4.pdf` in that directory. These are byte-identical copies of
the user-approved assets; the 320 × 245 mm layout was not resized or redrawn.

Read-only verification:

```sh
.venv/bin/python -B Figure/Fig4/publish_approved.py
```

`approved_composition.json` pins the approved images, data and rendering sources.
`publish_approved.py --publish-approved` is the dedicated initial adoption entry
point. Once this figure is current, that command only verifies the publication;
it will not silently adopt new renders. Future visual revisions need review.
The standard `manage.py approve` command does not apply to this asset adoption.

`run_plot.py` verifies the accepted composition figure. Legacy sensitivity R
sources remain as historical calculation code needed by Extended Data Fig. 3;
they are not the current Fig. 4 entrypoint. No legacy builder is run during cleanup.

The former Fig. 4 image, source tables, code and previous metadata are preserved
under `audit_archive/figure_maintenance/fig4_level1_adoption/` from the project
root. The original dated scientific tables also remain untouched. Sensitivity
analysis will be handled as a later figure; no Fig. 5 content was replaced.
