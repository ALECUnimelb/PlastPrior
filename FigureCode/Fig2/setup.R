source(file.path(module_dir,'style.R')); source(file.path(module_dir,'data.R')); source(file.path(module_dir,'plot_common.R'))
source(file.path(module_dir,'panels/coverage/data.R')); source(file.path(module_dir,'panels/coverage/plot.R'))
for (id in names(pbmt_dimension_schema)) {
 for (file in c('data.R','agreement_severity/plot.R','score_matrix/plot.R','assemble.R')) source(file.path(module_dir,'panels',id,file))
}
source(file.path(module_dir,'assemble.R'))
