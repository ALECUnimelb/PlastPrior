source('FigureCode/_shared/current.R')
source(file.path(module_dir,'setup.R'))
input <- read_policy_concordance_input(list(row_count=as.integer(lock$ranked)),config)
prepared <- prepare_policy_concordance_data(input,config)
save_nested(prepared$source_data);save_nested(prepared$audit_tables)
save_facts(c(prepared$statistics,list(full_inventory=lock$total,cohort='Fixed baseline rankable population, including partial evidence; missing components contribute zero.',capture_ties='Linear interpolation within tied-score groups; expected capture at matched screening size, not the official inclusive Top-N selection.',interval='Wilson 95% intervals for proportions; log-Wald 95% intervals for odds ratios.',strong_action_statuses=config$strong_action_statuses,stability_definition=config$stable_high_definition,stability_thresholds=config$thresholds)))

save_plot_data(list(prepared=prepared))
