assert_output_directory_is_new <- function(path) {
  if (dir.exists(path)) {
    entries <- list.files(path, all.files = TRUE, no.. = TRUE)
    if (length(entries) > 0L) {
      stop("Output directory must be new or empty: ", path, call. = FALSE)
    }
  } else if (file.exists(path)) {
    stop("Output path exists and is not a directory: ", path, call. = FALSE)
  }
}

assert_columns <- function(table, required_columns, table_name) {
  missing_columns <- setdiff(required_columns, names(table))
  if (length(missing_columns) > 0L) {
    stop(
      table_name, " is missing required column(s): ",
      paste(missing_columns, collapse = ", "),
      call. = FALSE
    )
  }
}

assert_discrete_numeric <- function(values, allowed, column_name, allow_missing = FALSE) {
  numeric_values <- suppressWarnings(as.numeric(values))
  original_present <- !is.na(values) & nzchar(trimws(as.character(values)))
  invalid <- original_present & (!is.finite(numeric_values) | is.na(numeric_values))
  if (any(invalid)) {
    stop(column_name, " contains invalid numeric values.", call. = FALSE)
  }
  if (!allow_missing && any(!original_present)) {
    stop(column_name, " contains missing values.", call. = FALSE)
  }
  observed <- numeric_values[!is.na(numeric_values)]
  supported <- vapply(
    observed,
    function(value) any(abs(value - allowed) <= 1e-9),
    logical(1)
  )
  if (!all(supported)) {
    stop(
      column_name, " contains values outside the declared score levels: ",
      paste(sort(unique(observed[!supported])), collapse = ", "),
      call. = FALSE
    )
  }
  numeric_values
}

relative_file_records <- function(root, exclude = character()) {
  files <- list.files(root, recursive = TRUE, full.names = TRUE, all.files = TRUE)
  files <- files[file.info(files)$isdir %in% FALSE]
  files <- setdiff(files, exclude)
  lapply(sort(files), function(path) {
    relative <- substring(normalizePath(path), nchar(normalizePath(root)) + 2L)
    list(
      path = gsub("\\\\", "/", relative),
      bytes = unname(file.info(path)$size),
      sha256 = sha256_file(path)
    )
  })
}

git_revision <- function(repo_root) {
  git <- Sys.which("git")
  if (!nzchar(git)) {
    return(list(commit = NULL, dirty = NULL))
  }
  # A distributed Figures bundle need not be inside a Git checkout. Do not
  # inherit an unrelated parent repository's revision or index an empty result.
  top <- suppressWarnings(system2(
    git, c("-C", shQuote(repo_root), "rev-parse", "--show-toplevel"),
    stdout = TRUE, stderr = FALSE
  ))
  if (length(top) != 1L || !is.null(attr(top, "status")) ||
      !identical(normalizePath(top, winslash = "/"),
                 normalizePath(repo_root, winslash = "/"))) {
    return(list(commit = NULL, dirty = NULL))
  }
  commit <- suppressWarnings(system2(git, c("-C", shQuote(repo_root), "rev-parse", "HEAD"), stdout = TRUE, stderr = FALSE))
  if (length(commit) != 1L || !is.null(attr(commit, "status"))) {
    return(list(commit = NULL, dirty = NULL))
  }
  status <- system2(git, c("-C", shQuote(repo_root), "status", "--porcelain"), stdout = TRUE, stderr = FALSE)
  list(commit = commit[[1]], dirty = length(status) > 0L)
}
