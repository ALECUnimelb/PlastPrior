source(file.path(module_dir,'style.R'));source(file.path(module_dir,'data.R'));source(file.path(module_dir,'assemble.R'))
ids <- c('strong_action_prevalence','ranking_capture','stable_review_context','analytical_annotation_gaps')
for(id in ids) source(file.path(module_dir,'panels',id,'plot.R'))
