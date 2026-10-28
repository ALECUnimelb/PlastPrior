#!/usr/bin/env Rscript
source('FigureCode/_shared/current.R')
source(file.path(module_dir,'setup.R'))
load_plot_data()
plots <- list(positive_input_breadth=plot_priority_positive_input_breadth(prepared$source_data$positive_input_breadth,config),positive_input_prevalence=plot_priority_positive_input_prevalence(prepared$source_data$positive_input_prevalence,config))
save_plot(assemble_priority_positive_input_context(plots,config),183,76)
