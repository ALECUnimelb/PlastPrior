source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
snapshot <- list(row_count=as.integer(lock$total),analysis_run_id=lock$run_id)
compounds <- read_pbmt_concordance_input(snapshot,config)
prepared <- prepare_pbmt_source_data(compounds,snapshot,config)
save_nested(prepared$source_data)
save_facts(list(population=lock$total,coverage=prepared$source_data$coverage_metrics,agreement=prepared$source_data$agreement_metrics,independent_evidence='Usable computational candidates after identity isolation; B comparison uses selected QSAR BCF only. Structural halogen rules remain part of final B selection.',missing='Unavailable candidates remain NA; paired statistics require both candidates.'))

save_plot_data(list(prepared=prepared))
