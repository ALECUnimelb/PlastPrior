# Snapshot discovery and loading helpers

find_latest_result_snapshot <- function(repo_root) {
  results_dir <- file.path(repo_root, "Result")
  if (!dir.exists(results_dir)) {
    stop("Result directory not found at: ", results_dir, call. = FALSE)
  }
  
  # Find all subdirectories matching timestamp pattern or folder entries
  dirs <- list.dirs(results_dir, recursive = FALSE, full.names = TRUE)
  # Filter to directories that contain 07. Prioritization/analysis_snapshot
  valid_snapshots <- character()
  for (d in dirs) {
    candidate <- file.path(d, "07. Prioritization", "analysis_snapshot")
    if (file.exists(file.path(candidate, "ChemicalPrio_compounds.csv")) &&
        file.exists(file.path(candidate, "ChemicalPrio_audit.sqlite"))) {
      valid_snapshots <- c(valid_snapshots, candidate)
    }
  }
  
  if (length(valid_snapshots) == 0L) {
    stop("No valid analysis_snapshot found in ", results_dir, call. = FALSE)
  }
  
  # Sort to pick the latest timestamp folder
  sorted_snapshots <- sort(valid_snapshots, decreasing = TRUE)
  sorted_snapshots[[1]]
}

read_snapshot_sql_query <- function(audit_path, query) {
  if (!is.character(query) || length(query) != 1L || !nzchar(trimws(query))) {
    stop("Snapshot SQL query must be one non-empty string.", call. = FALSE)
  }
  if (!file.exists(audit_path)) {
    stop("Snapshot audit database is missing: ", audit_path, call. = FALSE)
  }

  if (requireNamespace("DBI", quietly = TRUE) && requireNamespace("RSQLite", quietly = TRUE)) {
    connection <- DBI::dbConnect(
      RSQLite::SQLite(),
      dbname = audit_path,
      flags = RSQLite::SQLITE_RO
    )
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    return(DBI::dbGetQuery(connection, query))
  }

  sqlite_executable <- Sys.which("sqlite3")
  if (!nzchar(sqlite_executable)) {
    stop(
      "Reading snapshot audit tables requires either R packages DBI + RSQLite ",
      "or the sqlite3 command-line tool. On Windows, install.packages(c(\"DBI\", \"RSQLite\")) is recommended.",
      call. = FALSE
    )
  }
  output <- system2(
    sqlite_executable,
    c("-readonly", "-header", "-csv", shQuote(audit_path), shQuote(query)),
    stdout = TRUE,
    stderr = TRUE
  )
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop(
      "sqlite3 failed to read the snapshot audit: ",
      paste(output, collapse = "\n"),
      call. = FALSE
    )
  }
  if (length(output) == 0L) {
    return(data.frame())
  }
  readr::read_csv(
    paste(output, collapse = "\n"),
    col_types = readr::cols(.default = readr::col_character()),
    show_col_types = FALSE,
    progress = FALSE
  )
}

load_snapshot <- function(snapshot_dir) {
  root <- normalizePath(snapshot_dir, mustWork = TRUE)
  compounds_path <- file.path(root, "ChemicalPrio_compounds.csv")
  audit_path <- file.path(root, "ChemicalPrio_audit.sqlite")
  manifest_path <- file.path(root, "analysis_manifest.json")
  
  if (!file.exists(compounds_path)) {
    stop("ChemicalPrio_compounds.csv missing in ", root, call. = FALSE)
  }
  if (!file.exists(audit_path)) {
    stop("ChemicalPrio_audit.sqlite missing in ", root, call. = FALSE)
  }
  
  manifest <- list()
  if (file.exists(manifest_path)) {
    manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
  }
  
  list(
    root = root,
    compounds_path = compounds_path,
    audit_path = audit_path,
    manifest_path = manifest_path,
    manifest = manifest
  )
}
