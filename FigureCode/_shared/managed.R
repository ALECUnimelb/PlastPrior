# Current rounded scores and retained evidence; five-level labels are figure-only.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==1L)
module_dir <- dirname(normalizePath(sub('^--file=','',grep('^--file=',commandArgs(FALSE),value=TRUE)[1])))
figures_dir <- dirname(module_dir)
repo_root <- dirname(figures_dir)
shared_dir <- file.path(figures_dir,'_shared')
output_dir <- args[[1]]
for(f in c('palette.R','theme.R','export.R','validation.R')) source(file.path(shared_dir,f))
library(ggplot2)
library(patchwork)
lock <- jsonlite::fromJSON(file.path(figures_dir,'managed_sources.json'),simplifyVector=FALSE)
figure_policy <- jsonlite::fromJSON(file.path(repo_root,lock$policy$path),simplifyVector=FALSE)
db <- NULL
if (Sys.getenv("PLASTPRIOR_FIGURE_PHASE") == "prepare") db <- DBI::dbConnect(RSQLite::SQLite(),file.path(repo_root,lock$files$analysis$path),flags=RSQLite::SQLITE_RO)
config <- if(file.exists(file.path(module_dir,'figure.yml'))) jsonlite::fromJSON(file.path(module_dir,'figure.yml'),simplifyVector=FALSE) else NULL
level_for <- function(h,e) {
  h <- suppressWarnings(as.numeric(h)); e <- suppressWarnings(as.numeric(e))
  if(length(h)!=length(e) || any(!is.finite(c(h,e))) || any(!c(h,e) %in% 0:16)) stop('Expected rounded H/E scores in 0..16')
  cuts <- as.numeric(unlist(figure_policy$cutpoints))
  matrix_levels <- do.call(rbind,lapply(figure_policy$level_matrix_L_M_H_vH,unlist))
  as.integer(matrix_levels[cbind(findInterval(h,cuts)+1L,findInterval(e,cuts)+1L)])
}
apply_figure_levels <- function(frame) {
  frame$Priority_level <- level_for(frame$Hazard_score,frame$Exposure_score)
  frame$Priority_tier <- paste('Level',frame$Priority_level)
  frame
}
read_current <- function(fields,cohort='all') {
  aliases <- c(Inchikey_std='inchikey',Name_std='Name')
  requested <- fields
  if(any(c('Priority_tier','Priority_level') %in% fields)) fields <- unique(c(fields,'Hazard_score','Exposure_score'))
  canonical <- DBI::dbListFields(db,'current_compounds')
  publication <- DBI::dbListFields(db,'scenario_results')
  expressions <- vapply(fields,function(field) {
    key <- if(field %in% names(aliases)) aliases[[field]] else field
    table <- if(key %in% publication) 'p' else if(key %in% canonical) 'c' else stop('Unavailable field: ',field)
    paste0(table,'.',DBI::dbQuoteIdentifier(db,key),' AS ',DBI::dbQuoteIdentifier(db,field))
  },character(1))
  where <- switch(cohort,all='',ranked=" WHERE p.Ranking_eligible = 1 OR p.Ranking_eligible = 'True'",stop('Unsupported cohort'))
  frame <- DBI::dbGetQuery(db,paste0('SELECT ',paste(expressions,collapse=','),' FROM current_compounds c JOIN scenario_results p USING(inchikey)',where,' ORDER BY c.inchikey'))
  for(f in names(frame)) if(is.character(frame[[f]])) frame[[f]][frame[[f]]==''] <- NA_character_
  if(any(c('Priority_tier','Priority_level') %in% requested)) frame <- apply_figure_levels(frame)
  frame[,requested,drop=FALSE]
}
strict_numeric <- function(x,field,allow_missing=TRUE) {
  y <- suppressWarnings(as.numeric(x))
  if(any(!is.na(x)&(is.na(y)|!is.finite(y)))) stop('Invalid numeric value: ',field)
  if(!allow_missing&&anyNA(y)) stop('Missing required evidence: ',field)
  y
}
save_table <- function(data,name) {
  path <- file.path(output_dir,'source_data',paste0(name,'.csv'))
  dir.create(dirname(path),recursive=TRUE,showWarnings=FALSE)
  readr::write_csv(data,path,na='')
}
save_nested <- function(tables,prefix='') {
  for(name in names(tables)) {
    if(is.data.frame(tables[[name]])) save_table(tables[[name]],paste0(prefix,name))
    else if(is.list(tables[[name]])) save_nested(tables[[name]],paste0(prefix,name,'/'))
  }
}
save_facts <- function(facts) write_json_utf8(facts,file.path(output_dir,'caption_facts.json'))
save_plot <- function(plot,width,height) {
  export_figure(plot,file.path(output_dir,basename(module_dir)),width,height,dpi=600,formats=c('png','pdf'))
  # A temporary SVG is used only for the existing exact UpSet alignment audit.
  if(basename(module_dir)=='ExtendedDataFig1') export_figure(plot,file.path(output_dir,basename(module_dir)),width,height,formats='svg')
}

source(file.path(shared_dir,'plot_data.R'))
