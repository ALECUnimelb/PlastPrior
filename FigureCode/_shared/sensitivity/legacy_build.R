# Historical sensitivity recipe; source after current.R in a controlled staging build.
legacy_sensitivity_recipe <- function() {
module_dir <- file.path(shared_dir,'sensitivity')
config <- configure_current(jsonlite::fromJSON(file.path(module_dir,'figure.yml'),simplifyVector=FALSE))
source(file.path(module_dir,'style.R'));source(file.path(module_dir,'data.R'));source(file.path(module_dir,'assemble.R'))
ids <- c('leave_one_input_out','scenario_sensitivity')
for(id in ids) source(file.path(module_dir,'panels',id,'plot.R'))
input <- read_priority_sensitivity_input(list(row_count=as.integer(lock$ranked)),config)
prepared <- prepare_priority_sensitivity_data(input,config)
plots <- list(leave_one_input_out=plot_priority_leave_one_input_out(prepared$source_data$leave_one_input_out,config),scenario_sensitivity=plot_priority_scenario_sensitivity(prepared$source_data$scenario_sensitivity,config))
save_nested(prepared$source_data[ids]);save_nested(prepared$audit_tables)
save_facts(c(prepared$statistics,list(full_inventory=lock$total,cohort_rule='Fixed baseline Ranking_eligible=True population; missing components contribute zero while source missingness is retained. Ablation deliberately removes a contribution, without rescaling.',scenarios=config$scenarios)))
save_plot(assemble_priority_sensitivity_and_robustness(plots,config),183,86)

}
