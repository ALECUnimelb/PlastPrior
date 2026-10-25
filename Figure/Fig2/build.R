#!/usr/bin/env Rscript

# Publication contract: theme_classic(base_size = 7, base_family = "Arial")
# is provided through style.R and _shared/theme.R. _shared/export.R performs
# svglite::svglite("figure.svg"), grDevices::cairo_pdf("figure.pdf"),
# ragg::agg_png("figure.png", res = 600), and
# ragg::agg_tiff("figure.tiff", res = 600). The final width_mm = 183 and
# height_mm = 170; every visual is drawn and assembled by R.

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
  values <- list(
    snapshot = NULL,
    output_dir = NULL,
    formats = "svg,pdf,png,tiff",
    panel = "all",
    variant = "publication"
  )
  index <- 1L
  while (index <= length(arguments)) {
    key <- switch(
      arguments[[index]],
      "--snapshot" = "snapshot",
      "--output-dir" = "output_dir",
      "--formats" = "formats",
      "--panel" = "panel",
      "--variant" = "variant",
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
      "--output-dir <new_output_directory> [--panel <semantic_id>|all] ",
      "[--variant publication|audit_all_values] ",
      "[--formats svg,pdf,png,tiff]",
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
source(file.path(module_dir, "style.R"), encoding = "UTF-8")
source(file.path(module_dir, "data.R"), encoding = "UTF-8")
source(file.path(module_dir, "plot_common.R"), encoding = "UTF-8")

source(file.path(module_dir, "panels", "coverage", "data.R"), encoding = "UTF-8")
source(file.path(module_dir, "panels", "coverage", "plot.R"), encoding = "UTF-8")
for (dimension_id in names(pbmt_dimension_schema)) {
  dimension_dir <- file.path(module_dir, "panels", dimension_id)
  source(file.path(dimension_dir, "data.R"), encoding = "UTF-8")
  source(file.path(dimension_dir, "agreement_severity", "plot.R"), encoding = "UTF-8")
  source(file.path(dimension_dir, "score_matrix", "plot.R"), encoding = "UTF-8")
  source(file.path(dimension_dir, "assemble.R"), encoding = "UTF-8")
}
source(
  file.path(module_dir, "diagnostics", "cross_dimension_summary", "plot.R"),
  encoding = "UTF-8"
)
source(
  file.path(module_dir, "diagnostics", "combined_score_matrices", "plot.R"),
  encoding = "UTF-8"
)
source(file.path(module_dir, "assemble.R"), encoding = "UTF-8")

require_r_packages(c(
  "digest", "ggplot2", "jsonlite", "patchwork", "ragg", "readr",
  "scales", "svglite", "systemfonts", "tidyselect"
))
arguments <- parse_arguments(commandArgs(trailingOnly = TRUE))
dimension_ids <- names(pbmt_dimension_schema)
atomic_ids <- unlist(lapply(
  dimension_ids,
  function(dimension_id) paste0(
    dimension_id, c("_agreement_severity", "_score_matrix")
  )
), use.names = FALSE)
diagnostic_ids <- c("cross_dimension_summary", "combined_score_matrices")
selectable_ids <- c("coverage", dimension_ids, atomic_ids, diagnostic_ids)
if (!(arguments$panel %in% c("all", selectable_ids))) {
  stop(
    "Unknown --panel value: ", arguments$panel,
    ". Valid values: all, ", paste(selectable_ids, collapse = ", "),
    call. = FALSE
  )
}
if (!(arguments$variant %in% c("publication", "audit_all_values"))) {
  stop("--variant must be publication or audit_all_values.", call. = FALSE)
}

config <- jsonlite::fromJSON(
  file.path(module_dir, "figure.yml"), simplifyVector = FALSE
)
if (!identical(config$module_id, "pbmt_plastchem_concordance") ||
    !identical(tolower(config$backend), "r")) {
  stop("figure.yml module_id or backend does not match this R module.", call. = FALSE)
}
configured_dimensions <- vapply(
  config$dimensions, function(item) item$dimension_id, character(1)
)
if (!identical(configured_dimensions, dimension_ids)) {
  stop("figure.yml dimension order or IDs disagree with data.R.", call. = FALSE)
}

snapshot <- validate_analysis_snapshot_r(
  arguments$snapshot,
  required_columns = pbmt_required_compact_fields()
)
compounds <- read_pbmt_concordance_input(snapshot, config)
prepared <- prepare_pbmt_source_data(compounds, snapshot, config)
reference_verified <- assert_pbmt_reference_results(prepared, snapshot, config)

output_dir <- normalizePath(arguments$output_dir, mustWork = FALSE)
assert_output_directory_is_new(output_dir)
dir.create(dirname(output_dir), recursive = TRUE, showWarnings = FALSE)
staging_dir <- file.path(
  dirname(output_dir), paste0(".", basename(output_dir), ".building-", Sys.getpid())
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

write_source_data <- function(source_data, relative_dir) {
  destination <- file.path(staging_dir, "source_data", relative_dir)
  dir.create(destination, recursive = TRUE, showWarnings = FALSE)
  for (table_name in names(source_data)) {
    readr::write_csv(
      source_data[[table_name]],
      file.path(destination, paste0(table_name, ".csv")),
      na = ""
    )
  }
}

export_named_plot <- function(plot, relative_dir, stem, width_mm, height_mm) {
  output_stem <- if (identical(arguments$variant, "publication")) {
    stem
  } else {
    paste0(stem, "_audit_all_values")
  }
  export_figure(
    plot,
    file.path(staging_dir, relative_dir, output_stem),
    width_mm = width_mm,
    height_mm = height_mm,
    dpi = as.numeric(config$export$dpi),
    formats = arguments$formats
  )
}

wants <- function(id) {
  identical(arguments$panel, "all") || identical(arguments$panel, id)
}

panel_plots <- list()
panel_statistics <- list()
generated_exports <- character()

if (wants("coverage")) {
  coverage <- prepare_pbmt_coverage(prepared)
  write_source_data(coverage$source_data, "coverage")
  panel_statistics$coverage <- coverage$statistics
  panel_plots$coverage <- plot_pbmt_coverage(
    coverage$source_data, config, arguments$variant
  )
  generated_exports <- c(
    generated_exports,
    export_named_plot(
      panel_plots$coverage,
      file.path("panels", "coverage"),
      "coverage",
      as.numeric(config$export$coverage_width_mm),
      as.numeric(config$export$coverage_height_mm)
    )
  )
}

dimension_prepare_functions <- list(
  toxicity = prepare_pbmt_toxicity,
  bioaccumulation = prepare_pbmt_bioaccumulation,
  mobility = prepare_pbmt_mobility,
  persistence = prepare_pbmt_persistence
)
severity_plot_functions <- list(
  toxicity = plot_pbmt_toxicity_agreement_severity,
  bioaccumulation = plot_pbmt_bioaccumulation_agreement_severity,
  mobility = plot_pbmt_mobility_agreement_severity,
  persistence = plot_pbmt_persistence_agreement_severity
)
matrix_plot_functions <- list(
  toxicity = plot_pbmt_toxicity_score_matrix,
  bioaccumulation = plot_pbmt_bioaccumulation_score_matrix,
  mobility = plot_pbmt_mobility_score_matrix,
  persistence = plot_pbmt_persistence_score_matrix
)
assemble_functions <- list(
  toxicity = assemble_pbmt_toxicity,
  bioaccumulation = assemble_pbmt_bioaccumulation,
  mobility = assemble_pbmt_mobility,
  persistence = assemble_pbmt_persistence
)

for (dimension_id in dimension_ids) {
  severity_id <- paste0(dimension_id, "_agreement_severity")
  matrix_id <- paste0(dimension_id, "_score_matrix")
  wants_dimension <- wants(dimension_id)
  wants_severity <- wants_dimension || wants(severity_id)
  wants_matrix <- wants_dimension || wants(matrix_id)
  if (!(wants_severity || wants_matrix)) {
    next
  }
  dimension <- dimension_prepare_functions[[dimension_id]](prepared)
  panel_statistics[[dimension_id]] <- dimension$statistics
  if (wants_severity) {
    severity_source <- dimension$source_data[c(
      "agreement_band_summary", "agreement_metrics"
    )]
    write_source_data(
      severity_source, file.path(dimension_id, "agreement_severity")
    )
    severity_plot <- severity_plot_functions[[dimension_id]](
      severity_source, config, arguments$variant
    )
    panel_plots[[severity_id]] <- severity_plot
    generated_exports <- c(
      generated_exports,
      export_named_plot(
        severity_plot,
        file.path("panels", dimension_id, "agreement_severity"),
        severity_id,
        as.numeric(config$export$severity_width_mm),
        as.numeric(config$export$severity_height_mm)
      )
    )
  }
  if (wants_matrix) {
    matrix_source <- dimension$source_data[c("score_pair_matrix")]
    write_source_data(matrix_source, file.path(dimension_id, "score_matrix"))
    matrix_plot <- matrix_plot_functions[[dimension_id]](
      matrix_source, config, arguments$variant
    )
    panel_plots[[matrix_id]] <- matrix_plot
    generated_exports <- c(
      generated_exports,
      export_named_plot(
        matrix_plot,
        file.path("panels", dimension_id, "score_matrix"),
        matrix_id,
        as.numeric(config$export$matrix_width_mm),
        as.numeric(config$export$matrix_height_mm)
      )
    )
  }
  if (wants_dimension) {
    composite <- assemble_functions[[dimension_id]](
      panel_plots[[severity_id]], panel_plots[[matrix_id]], config
    )
    panel_plots[[dimension_id]] <- composite
    write_source_data(dimension$source_data, dimension_id)
    generated_exports <- c(
      generated_exports,
      export_named_plot(
        composite,
        file.path("panels", dimension_id),
        dimension_id,
        as.numeric(config$export$dimension_width_mm),
        as.numeric(config$export$dimension_height_mm)
      )
    )
  }
}

if (wants("cross_dimension_summary")) {
  source_data <- prepared$source_data[c(
    "agreement_band_summary", "agreement_metrics"
  )]
  write_source_data(source_data, file.path("diagnostics", "cross_dimension_summary"))
  plot <- plot_pbmt_cross_dimension_summary(source_data, config, arguments$variant)
  generated_exports <- c(
    generated_exports,
    export_named_plot(
      plot,
      file.path("diagnostics", "cross_dimension_summary"),
      "cross_dimension_summary",
      as.numeric(config$export$diagnostic_width_mm),
      as.numeric(config$export$diagnostic_height_mm)
    )
  )
}

if (wants("combined_score_matrices")) {
  source_data <- prepared$source_data[c("score_pair_matrix")]
  write_source_data(source_data, file.path("diagnostics", "combined_score_matrices"))
  plot <- plot_pbmt_combined_score_matrices(source_data, config, arguments$variant)
  generated_exports <- c(
    generated_exports,
    export_named_plot(
      plot,
      file.path("diagnostics", "combined_score_matrices"),
      "combined_score_matrices",
      as.numeric(config$export$diagnostic_width_mm),
      as.numeric(config$export$diagnostic_height_mm)
    )
  )
}

figure_exports <- character()
if (identical(arguments$panel, "all") && identical(arguments$variant, "publication")) {
  final_figure <- assemble_pbmt_concordance(panel_plots, config)
  figure_exports <- export_figure(
    final_figure,
    file.path(staging_dir, "figure", "pbmt_plastchem_concordance"),
    width_mm = as.numeric(config$export$width_mm),
    height_mm = as.numeric(config$export$height_mm),
    dpi = as.numeric(config$export$dpi),
    formats = arguments$formats
  )
  write_source_data(
    prepared$source_data[c(
      "coverage_summary", "coverage_metrics", "agreement_band_summary",
      "agreement_metrics", "score_pair_matrix", "comparison_status_counts",
      "comparison_source_counts"
    )],
    "figure"
  )
  write_source_data(
    prepared$source_data[c("compound_comparison")],
    "audit"
  )
}

caption_facts <- list(
  population_total = snapshot$row_count,
  excluded_rows = 0L,
  dimensions = lapply(
    seq_len(nrow(prepared$source_data$coverage_metrics)),
    function(index) as.list(
      prepared$source_data$coverage_metrics[index, , drop = FALSE]
    )
  ),
  comparison = list(
    computational_score_levels = pbmt_computational_score_levels,
    plastchem_score_levels = pbmt_plastchem_score_levels,
    exact_tolerance = as.numeric(config$thresholds$exact_tolerance),
    near_difference_max = as.numeric(config$thresholds$near_difference_max),
    moderate_difference_max = as.numeric(config$thresholds$moderate_difference_max),
    bioaccumulation_primary = "selected QSAR BCF",
    bioaccumulation_structural_rule_role = "sensitivity only"
  )
)
write_json_utf8(caption_facts, file.path(staging_dir, "audit", "caption_facts.json"))

revision <- git_revision(repo_root)
is_complete_publication <- identical(arguments$panel, "all") &&
  identical(arguments$variant, "publication")
qa <- list(
  passed = TRUE,
  release_eligible = (
    is_complete_publication && isFALSE(revision$dirty) &&
      identical(config$parity_status, "approved")
  ),
  checks = list(
    snapshot_hashes_verified = TRUE,
    snapshot_csv_sqlite_identity_verified = TRUE,
    evidence_json_validated = TRUE,
    selected_final_scores_crosschecked = TRUE,
    population_conserved_per_dimension = TRUE,
    shared_pairs_conserved_in_bands_and_matrices = TRUE,
    accepted_reference_totals_verified = isTRUE(reference_verified),
    bioaccumulation_structural_rule_excluded_from_primary_computational_series = TRUE,
    excluded_rows = 0L,
    selected_panel = arguments$panel,
    variant = arguments$variant,
    final_figure_assembled = length(figure_exports) > 0L,
    rendering_backend = "R"
  ),
  notes = if (!identical(config$parity_status, "approved")) {
    "Build passed data and rendering checks; manuscript-owner visual parity approval remains pending."
  } else if (isTRUE(revision$dirty)) {
    "Build passed checks but was produced from uncommitted figure code."
  } else if (!is_complete_publication) {
    "Standalone panel or audit variant passed; it is not a complete publication release."
  } else {
    "Build passed from committed figure code and an authenticated snapshot."
  }
)
write_json_utf8(qa, file.path(staging_dir, "audit", "qa_report.json"))

module_code_files <- list.files(
  module_dir, pattern = "\\.(R|yml|md)$", recursive = TRUE, full.names = TRUE
)
code_files <- c(
  module_code_files,
  list.files(shared_dir, pattern = "\\.R$", full.names = TRUE)
)
code_records <- lapply(sort(code_files), function(path) {
  relative <- substring(normalizePath(path), nchar(repo_root) + 2L)
  list(path = gsub("\\\\", "/", relative), sha256 = sha256_file(path))
})
manifest_path <- file.path(staging_dir, "audit", "figure_manifest.json")
manifest <- list(
  schema_version = 1,
  module_id = config$module_id,
  manuscript_slot = config$manuscript_slot,
  destination = config$destination,
  generated_at_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  backend = "R",
  requested_panel = arguments$panel,
  variant = arguments$variant,
  runtime = list(
    r_version = R.version.string,
    platform = R.version$platform,
    packages = list(
      ggplot2 = as.character(utils::packageVersion("ggplot2")),
      patchwork = as.character(utils::packageVersion("patchwork")),
      ragg = as.character(utils::packageVersion("ragg")),
      readr = as.character(utils::packageVersion("readr")),
      svglite = as.character(utils::packageVersion("svglite")),
      systemfonts = as.character(utils::packageVersion("systemfonts"))
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
    excluded_rows = 0L,
    parity_status = config$parity_status,
    stable_panel_ids = selectable_ids,
    panel_letters_are_assembly_only = TRUE,
    bioaccumulation_primary = "selected QSAR BCF",
    bioaccumulation_structural_rule_role = "sensitivity only",
    final_scores_crosschecked_against_evidence = TRUE
  ),
  key_results = caption_facts,
  panel_statistics = panel_statistics,
  code = code_records,
  generated_files = relative_file_records(staging_dir, exclude = manifest_path),
  qa = qa
)
write_json_utf8(manifest, manifest_path)

if (!file.rename(staging_dir, output_dir)) {
  stop("Could not atomically publish the completed figure output directory.", call. = FALSE)
}
completed <- TRUE
message("PBMT concordance output written to: ", normalizePath(output_dir, mustWork = TRUE))
