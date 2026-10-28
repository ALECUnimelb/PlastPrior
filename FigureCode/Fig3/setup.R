for(f in c('style.R','data.R','assemble.R')) source(file.path(module_dir,f))
ids <- c('priority_score_distribution','regulatory_context_inset','hazard_component_profiles','exposure_component_profiles')
for(id in ids) for(f in c('data.R','plot.R')) source(file.path(module_dir,'panels',id,f))
config <- jsonlite::fromJSON(file.path(module_dir,'figure.yml'),simplifyVector=FALSE)
config$priority_palette <- figure_policy$priority_palette
config$layout$row_heights <- c(65,85,68)
config$layout$inset$bottom <- .32
