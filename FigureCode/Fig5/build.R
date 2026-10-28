#!/usr/bin/env Rscript
source('FigureCode/_shared/current.R')
source(file.path(module_dir,'setup.R'))
load_plot_data()
plots <- lapply(setNames(ids,ids),function(id) get(paste0('plot_policy_',id))(prepared$source_data[[id]],config))
save_plot(assemble_policy_concordance_and_review_gaps(plots,config),183,150)
