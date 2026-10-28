# Locked, read-only current-analysis access. Empty numeric fields remain NA.
args <- commandArgs(trailingOnly = TRUE)
module_dir <- dirname(normalizePath(sub('^--file=', '', grep('^--file=', commandArgs(FALSE), value=TRUE)[1])))
figures_dir <- dirname(module_dir)
repo_root <- dirname(figures_dir)
shared_dir <- file.path(figures_dir, '_shared')
output_dir <- args[[1]]
source(file.path(shared_dir, 'palette.R'))
source(file.path(shared_dir, 'theme.R'))
source(file.path(shared_dir, 'export.R'))
source(file.path(shared_dir, 'validation.R'))
source(file.path(shared_dir, 'priority_policy.R'))
source(file.path(shared_dir, 'scenarios.R'))
library(ggplot2)
library(patchwork)
lock <- jsonlite::fromJSON(file.path(figures_dir, 'figure_sources.json'), simplifyVector=FALSE)
db <- NULL
if (Sys.getenv("PLASTPRIOR_FIGURE_PHASE") == "prepare") db <- DBI::dbConnect(RSQLite::SQLite(), file.path(repo_root, lock$files$analysis$path), flags=RSQLite::SQLITE_RO)
config <- if (file.exists(file.path(module_dir, 'figure.yml'))) jsonlite::fromJSON(file.path(module_dir, 'figure.yml'), simplifyVector=FALSE) else NULL
read_current <- function(fields, cohort='all') {
  aliases <- c(Inchikey_std='inchikey', Name_std='Name', source_dbs='source_dbs')
  publication <- DBI::dbListFields(db, 'publication_results')
  canonical <- DBI::dbListFields(db, 'compounds')
  expressions <- vapply(fields, function(field) {
    key <- if (field %in% names(aliases)) aliases[[field]] else field
    table <- if (key %in% canonical) 'c' else if (key %in% publication) 'p' else stop('Unavailable field: ',field)
    paste0(table,'.',DBI::dbQuoteIdentifier(db,key),' AS ',DBI::dbQuoteIdentifier(db,field))
  }, character(1))
  where <- switch(cohort, all='', ranked=" WHERE c.Ranking_eligible = 1", exposure=" WHERE c.Exposure_complete = 'True'", stop('Unknown cohort'))
  frame <- DBI::dbGetQuery(db, paste0('SELECT ',paste(expressions,collapse=','),' FROM compounds c JOIN publication_results p USING(inchikey)',where,' ORDER BY c.inchikey'))
  for (field in names(frame)) if(is.character(frame[[field]])) frame[[field]][frame[[field]]==''] <- NA_character_
  frame
}
strict_numeric <- function(x, field, allow_missing=TRUE) {
  y <- suppressWarnings(as.numeric(x))
  if (any(!is.na(x) & (is.na(y) | !is.finite(y)))) stop('Invalid numeric value: ',field)
  if (!allow_missing && anyNA(y)) stop('Missing required evidence: ',field)
  y
}
save_table <- function(data, name) {
  path <- file.path(output_dir,'source_data',paste0(name,'.csv'))
  dir.create(dirname(path),recursive=TRUE,showWarnings=FALSE)
  readr::write_csv(data,path,na='')
}
save_facts <- function(facts) jsonlite::write_json(facts,file.path(output_dir,'caption_facts.json'),pretty=TRUE,auto_unbox=TRUE,na='null')
save_plot <- function(plot, width, height) {
  export_figure(plot,file.path(output_dir,basename(module_dir)),width_mm=width,height_mm=height,dpi=600,formats=c('pdf','png'))
}
save_nested <- function(tables, prefix='') {
  for(name in names(tables)) {
    path <- paste0(prefix,name)
    if(is.data.frame(tables[[name]])) save_table(tables[[name]],path) else if(is.list(tables[[name]])) save_nested(tables[[name]],paste0(path,'/'))
  }
}
current_policy <- jsonlite::fromJSON(file.path(repo_root,'plastprior/priority_policy.json'),simplifyVector=FALSE)
configure_current <- function(config) {
  config$priority_tier_policy_version <- current_policy$policy_version
  high <- current_policy$tiers[['High priority']]
  moderate <- current_policy$tiers[['Moderate priority']]$any_of
  config$thresholds$moderate_hazard_min <- moderate[[1]]$hazard_gte
  config$thresholds$high_hazard_gt <- high$hazard_gt
  config$thresholds$exposure_min <- high$exposure_gte
  stopifnot(moderate[[1]]$hazard_lte == high$hazard_gt,
            moderate[[1]]$exposure_gte == high$exposure_gte,
            moderate[[2]]$hazard_gt == high$hazard_gt,
            moderate[[2]]$exposure_lt == high$exposure_gte)
  config
}
if(!is.null(config)) config <- configure_current(config)

source(file.path(shared_dir,'plot_data.R'))
