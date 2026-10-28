source('FigureCode/_shared/current.R')
source(file.path(module_dir,'setup.R'))
input <- read_priority_sensitivity_input(list(row_count=as.integer(lock$ranked)),config)
prepared <- prepare_priority_sensitivity_data(input,config,include_sensitivity=FALSE)
save_nested(prepared$source_data);save_nested(prepared$audit_tables)
save_facts(c(prepared$statistics,list(full_inventory=lock$total,breadth=prepared$source_data$positive_input_breadth$positive_input_breadth_metrics,missing='Full rankable population including partial evidence; positive means an available score greater than zero, not evidence completeness.')))

save_plot_data(list(prepared=prepared))
