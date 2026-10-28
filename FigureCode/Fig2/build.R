#!/usr/bin/env Rscript
source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
load_plot_data()
plots <- list(coverage=plot_pbmt_coverage(prepare_pbmt_coverage(prepared)$source_data,config,'publication'))
for(id in names(pbmt_dimension_schema)) {
 d <- get(paste0('prepare_pbmt_',id))(prepared)
 plots[[paste0(id,'_agreement_severity')]] <- get(paste0('plot_pbmt_',id,'_agreement_severity'))(d$source_data,config,'publication')
 plots[[paste0(id,'_score_matrix')]] <- get(paste0('plot_pbmt_',id,'_score_matrix'))(d$source_data,config,'publication')
}
# Assemble before opening the PDF device: lazy evaluation inside export can
# switch the active grid device and leave the first output page blank.
assembled <- assemble_pbmt_concordance(plots,config)
save_plot(assembled,183,170)
