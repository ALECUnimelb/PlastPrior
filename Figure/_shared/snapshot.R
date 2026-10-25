snapshot_file_names <- list(
  compounds = "ChemicalPrio_compounds.csv",
  audit = "ChemicalPrio_audit.sqlite",
  manifest = "analysis_manifest.json"
)

supported_snapshot_schema_versions <- c(1L, 2L)

read_snapshot_manifest <- function(snapshot_dir) {
  manifest_path <- file.path(snapshot_dir, snapshot_file_names$manifest)
  if (!file.exists(manifest_path)) {
    stop("Snapshot manifest is missing: ", manifest_path, call. = FALSE)
  }
  manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
  schema_version <- as.integer(manifest$snapshot_schema_version)
  if (!schema_version %in% supported_snapshot_schema_versions) {
    stop(
      "Unsupported snapshot schema version: ",
      manifest$snapshot_schema_version,
      call. = FALSE
    )
  }
  manifest
}

sqlite_snapshot_facts <- function(audit_path) {
  if (requireNamespace("DBI", quietly = TRUE) && requireNamespace("RSQLite", quietly = TRUE)) {
    connection <- DBI::dbConnect(
      RSQLite::SQLite(),
      dbname = audit_path,
      flags = RSQLite::SQLITE_RO
    )
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    integrity <- DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]][[1]]
    user_version <- DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]
    run_id <- DBI::dbGetQuery(
      connection,
      "SELECT value FROM snapshot_metadata WHERE key='analysis_run_id'"
    )[[1]][[1]]
    keys <- DBI::dbGetQuery(
      connection,
      "SELECT inchikey_std FROM compound_audit ORDER BY inchikey_std"
    )[[1]]
    return(list(
      integrity = as.character(integrity),
      user_version = as.integer(user_version),
      run_id = as.character(run_id),
      keys = as.character(keys),
      backend = "RSQLite"
    ))
  }

  sqlite_executable <- Sys.which("sqlite3")
  if (!nzchar(sqlite_executable)) {
    stop(
      "Snapshot audit validation requires either R packages DBI + RSQLite or ",
      "the sqlite3 command-line tool. On Windows, install.packages(c(\"DBI\", ",
      "\"RSQLite\")) is the recommended fallback.",
      call. = FALSE
    )
  }
  query <- paste(
    "PRAGMA integrity_check;",
    "PRAGMA user_version;",
    "SELECT value FROM snapshot_metadata WHERE key='analysis_run_id';",
    "SELECT inchikey_std FROM compound_audit ORDER BY inchikey_std;",
    sep = " "
  )
  output <- system2(
    sqlite_executable,
    c("-batch", "-noheader", shQuote(audit_path), shQuote(query)),
    stdout = TRUE,
    stderr = TRUE
  )
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop("sqlite3 failed to validate the snapshot audit: ", paste(output, collapse = "\n"), call. = FALSE)
  }
  if (length(output) < 3L) {
    stop("sqlite3 returned an incomplete snapshot audit response.", call. = FALSE)
  }
  list(
    integrity = output[[1]],
    user_version = as.integer(output[[2]]),
    run_id = output[[3]],
    keys = output[-seq_len(3L)],
    backend = "sqlite3"
  )
}

validate_analysis_snapshot_r <- function(snapshot_dir, required_columns = character()) {
  require_r_packages(c("digest", "jsonlite", "readr", "tidyselect"))
  root <- normalizePath(snapshot_dir, mustWork = TRUE)
  manifest <- read_snapshot_manifest(root)
  expected_files <- list(
    compounds = snapshot_file_names$compounds,
    audit = snapshot_file_names$audit
  )
  paths <- list()
  for (file_id in names(expected_files)) {
    record <- manifest$files[[file_id]]
    if (is.null(record) || !identical(record$path, expected_files[[file_id]])) {
      stop("Snapshot manifest has an invalid ", file_id, " file path.", call. = FALSE)
    }
    path <- file.path(root, record$path)
    if (!file.exists(path)) {
      stop("Snapshot ", file_id, " file is missing: ", path, call. = FALSE)
    }
    observed_hash <- sha256_file(path)
    if (!identical(tolower(observed_hash), tolower(record$sha256))) {
      stop("Snapshot ", file_id, " SHA-256 mismatch.", call. = FALSE)
    }
    paths[[file_id]] <- path
  }

  header <- names(readr::read_csv(
    paths$compounds,
    n_max = 0,
    show_col_types = FALSE,
    progress = FALSE,
    locale = readr::locale(encoding = "UTF-8")
  ))
  contract_columns <- c(
    "Inchikey_std",
    "analysis_run_id",
    "snapshot_schema_version",
    "snapshot_row_count"
  )
  missing_contract_columns <- setdiff(contract_columns, header)
  if (length(missing_contract_columns) > 0L) {
    stop(
      "Snapshot CSV is missing identity-contract column(s): ",
      paste(missing_contract_columns, collapse = ", "),
      call. = FALSE
    )
  }
  original_fields <- as.character(unlist(
    manifest$priority_table$columns,
    use.names = FALSE
  ))
  csv_fields <- as.character(unlist(
    manifest$compound_csv_columns,
    use.names = FALSE
  ))
  available_fields <- unique(c(original_fields, csv_fields))
  missing_required_fields <- setdiff(required_columns, available_fields)
  if (length(missing_required_fields) > 0L) {
    stop(
      "Analysis snapshot is missing required field(s): ",
      paste(missing_required_fields, collapse = ", "),
      call. = FALSE
    )
  }
  identity <- readr::read_csv(
    paths$compounds,
    col_select = tidyselect::all_of(contract_columns),
    col_types = readr::cols(.default = readr::col_character()),
    show_col_types = FALSE,
    progress = FALSE,
    locale = readr::locale(encoding = "UTF-8")
  )
  keys <- toupper(trimws(identity$Inchikey_std))
  if (nrow(identity) == 0L || any(!nzchar(keys)) || anyDuplicated(keys)) {
    stop("Snapshot CSV compound identities are empty, missing, or duplicated.", call. = FALSE)
  }
  expected_rows <- as.integer(manifest$row_count)
  if (nrow(identity) != expected_rows) {
    stop("Snapshot CSV row count disagrees with the manifest.", call. = FALSE)
  }
  if (!identical(unique(identity$analysis_run_id), manifest$analysis_run_id)) {
    stop("Snapshot CSV analysis_run_id disagrees with the manifest.", call. = FALSE)
  }
  schema_version <- as.integer(manifest$snapshot_schema_version)
  if (!identical(
    unique(identity$snapshot_schema_version),
    as.character(schema_version)
  )) {
    stop("Snapshot CSV schema version is not supported.", call. = FALSE)
  }
  if (!identical(unique(identity$snapshot_row_count), as.character(expected_rows))) {
    stop("Snapshot CSV embedded row count disagrees with the manifest.", call. = FALSE)
  }

  audit <- sqlite_snapshot_facts(paths$audit)
  if (!identical(audit$integrity, "ok") ||
      !identical(audit$user_version, schema_version)) {
    stop("Snapshot SQLite integrity or schema validation failed.", call. = FALSE)
  }
  if (!identical(audit$run_id, manifest$analysis_run_id)) {
    stop("Snapshot SQLite analysis_run_id disagrees with the manifest.", call. = FALSE)
  }
  if (!identical(sort(unique(toupper(trimws(audit$keys)))), sort(unique(keys)))) {
    stop("Snapshot CSV and SQLite compound identities differ.", call. = FALSE)
  }

  list(
    root = root,
    compounds_path = paths$compounds,
    audit_path = paths$audit,
    manifest_path = file.path(root, snapshot_file_names$manifest),
    manifest = manifest,
    analysis_run_id = manifest$analysis_run_id,
    row_count = expected_rows,
    compounds_sha256 = manifest$files$compounds$sha256,
    audit_sha256 = manifest$files$audit$sha256,
    sqlite_validation_backend = audit$backend
  )
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
      "or the sqlite3 command-line tool. On Windows, install.packages(c(\"DBI\", ",
      "\"RSQLite\")) is the recommended fallback.",
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
