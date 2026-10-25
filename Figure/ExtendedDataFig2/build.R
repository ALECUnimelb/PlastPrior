#!/usr/bin/env Rscript

# Modular publication contract (implemented by _shared/theme.R and
# _shared/export.R): theme_classic(base_size = 7, base_family = "Arial"),
# svglite::svglite("figure.svg"), grDevices::cairo_pdf("figure.pdf"),
# ragg::agg_png("figure.png", res = 600), and
# ragg::agg_tiff("figure.tiff", res = 600), with final width_mm = 183.

script_directory <- function() {
  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) != 1L) {
    stop("Could not determine the figure module path.", call. = FALSE)
  }
  script_path <- sub("^--file=", "", file_arg[[1]])
  # R escapes spaces/newlines in the --file argument supplied to Rscript.
  script_path <- gsub("~[+]~", " ", script_path)
  script_path <- gsub("~n~", "\n", script_path)
  dirname(normalizePath(script_path, mustWork = TRUE))
}

parse_arguments <- function(arguments) {
  values <- list(snapshot = NULL, output_dir = NULL, formats = "svg,pdf,png,tiff")
  index <- 1L
  while (index <= length(arguments)) {
    key <- switch(
      arguments[[index]],
      "--snapshot" = "snapshot",
      "--output-dir" = "output_dir",
      "--formats" = "formats",
      stop("Unsupported argument: ", arguments[[index]], call. = FALSE)
    )
    if (index == length(arguments)) {
      stop("Missing value after ", arguments[[index]], call. = FALSE)
    }
    values[[key]] <- arguments[[index + 1L]]
    index <- index + 2L
  }
  if (is.null(values$snapshot) || is.null(values$output_dir)) {
    stop(
      "Usage: Rscript build.R --snapshot <analysis_snapshot_directory> ",
      "--output-dir <new_output_directory> [--formats svg,pdf,png,tiff]",
      call. = FALSE
    )
  }
  values$formats <- trimws(strsplit(values$formats, ",", fixed = TRUE)[[1]])
  values$formats <- values$formats[nzchar(values$formats)]
  values
}

module_dir <- script_directory()
figures_dir <- normalizePath(file.path(module_dir, ".."), mustWork = TRUE)
repo_root <- normalizePath(file.path(figures_dir, ".."), mustWork = TRUE)
shared_dir <- file.path(figures_dir, "_shared")
source(file.path(shared_dir, "palette.R"), encoding = "UTF-8")
source(file.path(shared_dir, "theme.R"), encoding = "UTF-8")
source(file.path(shared_dir, "export.R"), encoding = "UTF-8")
source(file.path(shared_dir, "snapshot.R"), encoding = "UTF-8")
source(file.path(shared_dir, "validation.R"), encoding = "UTF-8")
source(
  file.path(module_dir, "panels", "hazard_dimension_overlap", "plot.R"),
  encoding = "UTF-8"
)
source(
  file.path(module_dir, "panels", "exposure_dimension_overlap", "plot.R"),
  encoding = "UTF-8"
)
source(file.path(module_dir, "assemble.R"), encoding = "UTF-8")

require_r_packages(c(
  "digest", "ggplot2", "ggVennDiagram", "jsonlite", "patchwork",
  "ragg", "readr", "scales", "svglite", "tidyselect"
))
arguments <- parse_arguments(commandArgs(trailingOnly = TRUE))
config <- jsonlite::fromJSON(
  file.path(module_dir, "figure.yml"),
  simplifyVector = FALSE
)
if (!identical(config$module_id, "evidence_overlap_patterns")) {
  stop("figure.yml module_id does not match this module.", call. = FALSE)
}

required_columns <- c(
  "Inchikey_std",
  unname(hazard_score_columns),
  unique(unlist(exposure_score_columns, use.names = FALSE))
)
snapshot <- validate_analysis_snapshot_r(
  arguments$snapshot,
  required_columns = required_columns
)
compounds <- readr::read_csv(
  snapshot$compounds_path,
  col_select = tidyselect::all_of(required_columns),
  show_col_types = FALSE,
  progress = FALSE,
  locale = readr::locale(encoding = "UTF-8")
)
if (nrow(compounds) != snapshot$row_count) {
  stop("Figure input row count changed after snapshot validation.", call. = FALSE)
}

output_dir <- normalizePath(arguments$output_dir, mustWork = FALSE)
if (file.exists(output_dir)) {
  stop("Output directory must not already exist: ", output_dir, call. = FALSE)
}
dir.create(dirname(output_dir), recursive = TRUE, showWarnings = FALSE)
staging_dir <- file.path(
  dirname(output_dir),
  paste0(".", basename(output_dir), ".building-", Sys.getpid())
)
if (file.exists(staging_dir)) {
  stop("Temporary build directory already exists: ", staging_dir, call. = FALSE)
}
dir.create(staging_dir, recursive = TRUE, showWarnings = FALSE)
completed <- FALSE
on.exit({
  if (!completed && dir.exists(staging_dir)) {
    unlink(staging_dir, recursive = TRUE, force = TRUE)
  }
}, add = TRUE)

hazard_source_dir <- file.path(
  staging_dir, "source_data", "hazard_dimension_overlap"
)
exposure_source_dir <- file.path(
  staging_dir, "source_data", "exposure_dimension_overlap"
)
hazard <- prepare_hazard_overlap(compounds, hazard_source_dir)
exposure <- prepare_exposure_overlap(compounds, exposure_source_dir)

dpi <- as.numeric(config$export$dpi)
panel_exports <- c(
  export_figure(
    hazard$plot,
    file.path(staging_dir, "panels", "hazard_dimension_overlap", "hazard_dimension_overlap"),
    width_mm = 140,
    height_mm = 100,
    dpi = dpi,
    formats = arguments$formats
  ),
  export_figure(
    exposure$plot,
    file.path(staging_dir, "panels", "exposure_dimension_overlap", "exposure_dimension_overlap"),
    width_mm = 183,
    height_mm = 112,
    dpi = dpi,
    formats = arguments$formats
  )
)
assembled <- assemble_evidence_overlap_patterns(hazard$plot, exposure$plot)
figure_exports <- export_figure(
  assembled,
  file.path(staging_dir, "figure", "evidence_overlap_patterns"),
  width_mm = as.numeric(config$export$width_mm),
  height_mm = as.numeric(config$export$height_mm),
  dpi = dpi,
  formats = arguments$formats
)

caption_facts <- list(
  population_total = snapshot$row_count,
  hazard = list(
    none_count = hazard$statistics$none_count,
    all_four_count = hazard$statistics$all_four_count,
    membership_rule = hazard$statistics$membership_rule
  ),
  exposure = list(
    positive_union_count = exposure$statistics$positive_union_count,
    no_positive_indicator_count = exposure$statistics$no_positive_indicator_count,
    all_five_positive_count = exposure$statistics$all_five_positive_count,
    membership_rule = exposure$statistics$membership_rule
  )
)
write_json_utf8(caption_facts, file.path(staging_dir, "audit", "caption_facts.json"))

revision <- git_revision(repo_root)
qa <- list(
  passed = TRUE,
  release_eligible = (
    isFALSE(revision$dirty) && identical(config$parity_status, "approved")
  ),
  checks = list(
    snapshot_hashes_verified = TRUE,
    snapshot_csv_sqlite_identity_verified = TRUE,
    excluded_rows = 0,
    hazard_intersections_complete = hazard$statistics$intersection_count == 16L,
    hazard_population_conserved = hazard$statistics$intersection_sum == snapshot$row_count,
    exposure_intersections_complete = exposure$statistics$complete_intersection_count == 32L,
    exposure_population_conserved = exposure$statistics$complete_intersection_sum == snapshot$row_count,
    exposure_positive_union_conserved = (
      exposure$statistics$displayed_positive_intersection_sum ==
        exposure$statistics$positive_union_count
    ),
    rendering_backend = "R"
  ),
  notes = if (!identical(config$parity_status, "approved")) {
    "Build passed data and render checks; parity against the authenticated paper snapshot remains pending."
  } else if (isTRUE(revision$dirty)) {
    "Build passed data and render checks but was produced from uncommitted figure code."
  } else {
    "Build passed data and render checks from committed figure code."
  }
)
write_json_utf8(qa, file.path(staging_dir, "audit", "qa_report.json"))

code_files <- c(
  file.path(module_dir, "build.R"),
  file.path(module_dir, "assemble.R"),
  file.path(module_dir, "figure.yml"),
  file.path(module_dir, "methods.md"),
  file.path(module_dir, "panels", "hazard_dimension_overlap", "plot.R"),
  file.path(module_dir, "panels", "exposure_dimension_overlap", "plot.R"),
  list.files(shared_dir, pattern = "\\.R$", full.names = TRUE)
)
code_records <- lapply(sort(code_files), function(path) {
  relative <- substring(normalizePath(path), nchar(repo_root) + 2L)
  list(
    path = gsub("\\\\", "/", relative),
    sha256 = sha256_file(path)
  )
})
manifest_path <- file.path(staging_dir, "audit", "figure_manifest.json")
manifest <- list(
  schema_version = 1,
  module_id = config$module_id,
  manuscript_slot = config$manuscript_slot,
  destination = config$destination,
  generated_at_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  backend = "R",
  runtime = list(
    r_version = R.version.string,
    platform = R.version$platform,
    packages = list(
      ggplot2 = as.character(utils::packageVersion("ggplot2")),
      ggVennDiagram = as.character(utils::packageVersion("ggVennDiagram")),
      patchwork = as.character(utils::packageVersion("patchwork")),
      ragg = as.character(utils::packageVersion("ragg")),
      svglite = as.character(utils::packageVersion("svglite"))
    )
  ),
  snapshot = list(
    analysis_run_id = snapshot$analysis_run_id,
    row_count = snapshot$row_count,
    compounds_file = snapshot_file_names$compounds,
    compounds_sha256 = snapshot$compounds_sha256,
    audit_file = snapshot_file_names$audit,
    audit_sha256 = snapshot$audit_sha256,
    sqlite_validation_backend = snapshot$sqlite_validation_backend
  ),
  repository = revision,
  figure_contract = list(
    excluded_rows = 0,
    parity_status = config$parity_status,
    hazard_membership_rule = hazard$statistics$membership_rule,
    exposure_membership_rule = exposure$statistics$membership_rule
  ),
  key_results = caption_facts,
  code = code_records,
  generated_files = relative_file_records(staging_dir, exclude = manifest_path),
  qa = qa
)
write_json_utf8(manifest, manifest_path)

if (!file.rename(staging_dir, output_dir)) {
  stop("Could not atomically publish the completed figure output directory.", call. = FALSE)
}
completed <- TRUE
message("Evidence overlap figure written to: ", normalizePath(output_dir, mustWork = TRUE))
