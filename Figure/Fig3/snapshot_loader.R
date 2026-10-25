# Snapshot discovery and loading helpers for Priority Landscape

find_latest_result_snapshot <- function(repo_root) {
  results_dir <- file.path(repo_root, "Result")
  if (!dir.exists(results_dir)) {
    stop("Result directory not found at: ", results_dir, call. = FALSE)
  }
  
  dirs <- list.dirs(results_dir, recursive = FALSE, full.names = TRUE)
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
    I(paste(output, collapse = "\n")),
    col_types = readr::cols(.default = readr::col_character()),
    show_col_types = FALSE,
    progress = FALSE,
    locale = readr::locale(encoding = "UTF-8")
  )
}

quote_sqlite_identifier_r <- function(value) {
  paste0('"', gsub('"', '""', as.character(value), fixed = TRUE), '"')
}

read_analysis_snapshot_fields_r <- function(snapshot, fields) {
  fields <- unique(as.character(fields))
  if (length(fields) == 0L) {
    stop("At least one snapshot field must be requested.", call. = FALSE)
  }
  original_fields <- as.character(unlist(
    snapshot$manifest$priority_table$columns,
    use.names = FALSE
  ))
  csv_fields <- as.character(unlist(
    snapshot$manifest$compound_csv_columns,
    use.names = FALSE
  ))
  available_fields <- unique(c(original_fields, csv_fields))
  missing <- setdiff(fields, available_fields)
  if (length(missing) > 0L) {
    stop(
      "Analysis snapshot does not contain requested field(s): ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }

  csv_requested <- intersect(fields, csv_fields)
  csv_select <- unique(c("Inchikey_std", csv_requested))
  result <- readr::read_csv(
    snapshot$compounds_path,
    col_select = tidyselect::all_of(csv_select),
    col_types = readr::cols(.default = readr::col_character()),
    show_col_types = FALSE,
    progress = FALSE,
    locale = readr::locale(encoding = "UTF-8")
  )
  if (nrow(result) != snapshot$row_count || anyDuplicated(result$Inchikey_std)) {
    stop("Snapshot CSV identity changed during field loading.", call. = FALSE)
  }

  audit_requested <- setdiff(fields, csv_fields)
  if (length(audit_requested) > 0L) {
    query <- paste0(
      "SELECT inchikey_std, ",
      paste(
        vapply(audit_requested, quote_sqlite_identifier_r, character(1)),
        collapse = ", "
      ),
      " FROM compound_audit"
    )
    audit <- read_snapshot_sql_query(snapshot$audit_path, query)
    if (!"inchikey_std" %in% names(audit) ||
        nrow(audit) != snapshot$row_count || anyDuplicated(audit$inchikey_std)) {
      stop("Snapshot SQLite identity changed during field loading.", call. = FALSE)
    }
    row_index <- match(result$Inchikey_std, audit$inchikey_std)
    if (any(is.na(row_index))) {
      stop("Snapshot CSV and SQLite identities differ during field loading.", call. = FALSE)
    }
    for (field in audit_requested) {
      if (!field %in% names(audit)) {
        stop("Snapshot SQLite query omitted field: ", field, call. = FALSE)
      }
      result[[field]] <- as.character(audit[[field]][row_index])
    }
  }
  result[, fields, drop = FALSE]
}

load_priority_snapshot <- function(snapshot_dir) {
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
  
  row_count <- as.integer(manifest$row_count)
  if (length(row_count) != 1L || is.na(row_count)) {
    # CSV-aware fallback works on Windows as well as macOS; no Unix wc needed.
    row_count <- nrow(readr::read_csv(
      compounds_path, col_select = tidyselect::all_of("Inchikey_std"),
      col_types = readr::cols(.default = readr::col_character()),
      show_col_types = FALSE, progress = FALSE,
      locale = readr::locale(encoding = "UTF-8")
    ))
  }
  
  list(
    root = root,
    compounds_path = compounds_path,
    audit_path = audit_path,
    manifest_path = manifest_path,
    manifest = manifest,
    row_count = row_count
  )
}
