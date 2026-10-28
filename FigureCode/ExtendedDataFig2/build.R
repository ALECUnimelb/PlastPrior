#!/usr/bin/env Rscript
source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
load_plot_data()
hazard <- plot_hazard_overlap(hazard)
exposure <- plot_exposure_overlap(exposure)
save_plot(assemble_evidence_overlap_patterns(hazard$plot,exposure$plot),183,220)
