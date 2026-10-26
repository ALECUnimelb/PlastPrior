#!/usr/bin/env Rscript
source('Figure/_shared/current.R')
source(file.path(module_dir,'style.R')); source(file.path(module_dir,'data.R')); source(file.path(module_dir,'plot_common.R'))
source(file.path(module_dir,'panels/coverage/data.R')); source(file.path(module_dir,'panels/coverage/plot.R'))
for (id in names(pbmt_dimension_schema)) {
 for (file in c('data.R','agreement_severity/plot.R','score_matrix/plot.R','assemble.R')) source(file.path(module_dir,'panels',id,file))
}
source(file.path(module_dir,'assemble.R'))
snapshot <- list(row_count=as.integer(lock$total),analysis_run_id=lock$run_id)
compounds <- read_pbmt_concordance_input(snapshot,config)
prepared <- prepare_pbmt_source_data(compounds,snapshot,config)
plots <- list(coverage=plot_pbmt_coverage(prepare_pbmt_coverage(prepared)$source_data,config,'publication'))
for(id in names(pbmt_dimension_schema)) {
 d <- get(paste0('prepare_pbmt_',id))(prepared)
 plots[[paste0(id,'_agreement_severity')]] <- get(paste0('plot_pbmt_',id,'_agreement_severity'))(d$source_data,config,'publication')
 plots[[paste0(id,'_score_matrix')]] <- get(paste0('plot_pbmt_',id,'_score_matrix'))(d$source_data,config,'publication')
}
save_nested(prepared$source_data)
save_facts(list(population=lock$total,coverage=prepared$source_data$coverage_metrics,agreement=prepared$source_data$agreement_metrics,independent_evidence='Usable computational and structural candidates after identity isolation; B includes structural halogen rules.',missing='Unavailable candidates remain NA; paired statistics require both candidates.'))
save_plot(assemble_pbmt_concordance(plots,config),183,170)
