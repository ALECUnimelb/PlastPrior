# Numerical payloads are prepared explicitly and stored beside the CSV tables.
save_plot_data <- function(values) {
  stopifnot(Sys.getenv('PLASTPRIOR_FIGURE_PHASE') == 'prepare')
  dir.create(file.path(output_dir,'source_data'),recursive=TRUE,showWarnings=FALSE)
  saveRDS(values,file.path(output_dir,'source_data/plot_data.rds'),version=3)
}
load_plot_data <- function() {
  path <- file.path(output_dir,'source_data/plot_data.rds')
  if (!file.exists(path)) stop('Missing prepared figure data. Run FigureCode/prepare_data.py first.')
  list2env(readRDS(path),envir=.GlobalEnv)
}
