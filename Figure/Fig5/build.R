#!/usr/bin/env Rscript

# Publication contract: theme_classic(base_size = 7.2, base_family = "Arial")
# is applied through style.R and _shared/theme.R. _shared/export.R performs
# svglite::svglite("figure.svg"), grDevices::cairo_pdf("figure.pdf"),
# ragg::agg_png("figure.png", res = 600), and
# ragg::agg_tiff("figure.tiff", res = 600). The main composite is exported at
# width_mm = 183 and height_mm = 150; all plotting and assembly use R only.

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
    panel = "all"
  )
  index <- 1L
  while (index <= length(arguments)) {
    key <- switch(
      arguments[[index]],
      "--snapshot" = "snapshot",
      "--output-dir" = "output_dir",
      "--formats" = "formats",
      "--panel" = "panel",
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
source(file.path(shared_dir, "priority_policy.R"), encoding = "UTF-8")
source(file.path(module_dir, "style.R"), encoding = "UTF-8")
source(file.path(module_dir, "data.R"), encoding = "UTF-8")
source(
  file.path(module_dir, "panels", "strong_action_prevalence", "plot.R"),
  encoding = "UTF-8"
)
source(
  file.path(module_dir, "panels", "ranking_capture", "plot.R"),
  encoding = "UTF-8"
)
source(
  file.path(module_dir, "panels", "stable_review_context", "plot.R"),
  encoding = "UTF-8"
)
source(
  file.path(module_dir, "panels", "analytical_annotation_gaps", "plot.R"),
  encoding = "UTF-8"
)
source(file.path(module_dir, "assemble.R"), encoding = "UTF-8")

require_r_packages(c(
  "digest", "ggplot2", "jsonlite", "patchwork", "ragg", "readr",
  "scales", "svglite", "systemfonts", "tidyselect"
))
arguments <- parse_arguments(commandArgs(trailingOnly = TRUE))
config <- jsonlite::fromJSON(
  file.path(module_dir, "figure.yml"), simplifyVector = FALSE
)
if (!identical(config$module_id, "policy_concordance_and_review_gaps") ||
    !identical(tolower(config$backend), "r")) {
  stop("figure.yml module_id or backend does not match this R module.", call. = FALSE)
}
panel_ids <- vapply(config$panels, function(item) item$panel_id, character(1))
expected_panel_ids <- c(
  "strong_action_prevalence", "ranking_capture",
  "stable_review_context", "analytical_annotation_gaps"
)
if (!identical(panel_ids, expected_panel_ids)) {
  stop("figure.yml panel order or IDs disagree with the module contract.", call. = FALSE)
}
if (!(arguments$panel %in% c("all", panel_ids))) {
  stop(
    "Unknown --panel value: ", arguments$panel,
    ". Valid values: all, ", paste(panel_ids, collapse = ", "),
    call. = FALSE
  )
}

snapshot <- validate_analysis_snapshot_r(
  arguments$snapshot,
  required_columns = policy_required_fields(config)
)
config <- priority_config_for_snapshot(snapshot, config)
input <- read_policy_concordance_input(snapshot, config)
prepared <- prepare_policy_concordance_data(input, config)
reference_verified <- assert_policy_concordance_reference(
  prepared, snapshot, config
)

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

export_named_plot <- function(plot, panel_id) {
  panel_config <- policy_panel_config(config, panel_id)
  export_figure(
    plot,
    file.path(staging_dir, "panels", panel_id, panel_id),
    width_mm = as.numeric(panel_config$width_mm),
    height_mm = as.numeric(panel_config$height_mm),
    dpi = as.numeric(config$export$dpi),
    formats = arguments$formats
  )
}

wants <- function(panel_id) {
  identical(arguments$panel, "all") || identical(arguments$panel, panel_id)
}

plot_functions <- list(
  strong_action_prevalence = plot_policy_strong_action_prevalence,
  ranking_capture = plot_policy_ranking_capture,
  stable_review_context = plot_policy_stable_review_context,
  analytical_annotation_gaps = plot_policy_analytical_annotation_gaps
)
panel_plots <- list()
generated_exports <- character()
panel_statistics <- list()
for (panel_id in panel_ids) {
  if (!wants(panel_id)) {
    next
  }
  source_data <- prepared$source_data[[panel_id]]
  write_source_data(source_data, panel_id)
  panel_plots[[panel_id]] <- plot_functions[[panel_id]](source_data, config)
  generated_exports <- c(
    generated_exports,
    export_named_plot(panel_plots[[panel_id]], panel_id)
  )
  panel_statistics[[panel_id]] <- list(
    source_table_count = length(source_data),
    primary_row_count = nrow(source_data[[1]])
  )
  write_json_utf8(
    panel_statistics[[panel_id]],
    file.path(staging_dir, "audit", "panels", paste0(panel_id, ".json"))
  )
}

figure_exports <- character()
if (identical(arguments$panel, "all")) {
  final_figure <- assemble_policy_concordance_and_review_gaps(
    panel_plots, config
  )
  figure_exports <- export_figure(
    final_figure,
    file.path(
      staging_dir, "figure", "policy_concordance_and_review_gaps"
    ),
    width_mm = as.numeric(config$export$width_mm),
    height_mm = as.numeric(config$export$height_mm),
    dpi = as.numeric(config$export$dpi),
    formats = arguments$formats
  )
  figure_source <- list()
  for (panel_id in panel_ids) {
    figure_source <- c(figure_source, prepared$source_data[[panel_id]])
  }
  write_source_data(figure_source, "figure")
  write_source_data(prepared$audit_tables, "audit")
}

prevalence <-
  prepared$source_data$strong_action_prevalence$strong_action_prevalence
metrics <- prepared$source_data$ranking_capture$ranking_capture_metrics
caption_facts <- list(
  priority_tier_policy_version = config$priority_tier_policy_version,
  component_gates = list(moderate = config$thresholds$moderate_component_min,
                         high = config$thresholds$high_component_min),
  population_total = prepared$statistics$population_total,
  excluded_rows = prepared$statistics$excluded_rows,
  strong_action_endpoint = list(
    statuses = as.character(unlist(
      config$strong_action_statuses, use.names = FALSE
    )),
    compound_count = prepared$statistics$strong_action_count,
    directly_scored = FALSE,
    interpretation = "Policy concordance, not independent external validation",
    infrastructure_caveat = paste(
      "The endpoint and inventory-presence exposure proxy share GIC",
      "infrastructure but use non-overlapping list classes."
    )
  ),
  strong_action_prevalence = stats::setNames(
    as.list(prevalence$proportion), prevalence$priority_tier
  ),
  ranking_capture = stats::setNames(
    as.list(metrics$capture_at_high_priority_fraction), metrics$method
  ),
  stable_high_priority_definition = list(
    hazard_and_exposure_minimum_in_every_scenario = config$thresholds$high_component_min,
    baseline_score_at_least =
      as.numeric(config$thresholds$baseline_stable_minimum),
    alternative_scores_at_least =
      as.numeric(config$thresholds$alternative_stable_minimum),
    stable_high_priority_count = prepared$statistics$stable_high_priority_count,
    stable_outside_strong_action_count =
      prepared$statistics$stable_outside_strong_action_count
  ),
  analytical_annotation = list(
    stable_no_gic_listing_count =
      prepared$statistics$stable_no_gic_listing_count,
    without_norman_match =
      prepared$statistics$stable_no_gic_listing_without_norman_match,
    norman_matched_count = prepared$statistics$norman_matched_count,
    interpretation = paste(
      "Absence of a SusDat match is an annotation gap, not evidence of",
      "analytical impossibility."
    )
  ),
  review_queue_interpretation = paste(
    "Stable candidates are evidence-review queues, not validated hazards",
    "or policy recommendations."
  )
)
write_json_utf8(
  caption_facts,
  file.path(staging_dir, "audit", "caption_facts.json")
)

revision <- git_revision(repo_root)
is_complete <- identical(arguments$panel, "all")
qa <- list(
  passed = TRUE,
  release_eligible = (
    is_complete && isFALSE(revision$dirty) &&
      identical(config$parity_status, "approved")
  ),
  checks = list(
    snapshot_hashes_verified = TRUE,
    snapshot_csv_sqlite_identity_verified = TRUE,
    population_conserved = TRUE,
    hazard_score_reconstructed = TRUE,
    exposure_score_reconstructed = TRUE,
    priority_score_reconstructed = TRUE,
    priority_tiers_reconstructed = TRUE,
    strong_action_endpoint_prespecified = TRUE,
    strong_action_endpoint_not_directly_scored = TRUE,
    ranking_capture_is_tie_aware = TRUE,
    candidate_subsets_explicitly_identified = TRUE,
    accepted_reference_results_verified = if (is.na(reference_verified)) {
      NULL
    } else {
      isTRUE(reference_verified)
    },
    excluded_rows = 0L,
    selected_panel = arguments$panel,
    final_figure_assembled = length(figure_exports) > 0L,
    rendering_backend = "R"
  ),
  notes = if (!identical(config$parity_status, "approved") &&
              isTRUE(reference_verified)) {
    paste(
      "Build passed data, rendering, and accepted numerical reference checks;",
      "manuscript-owner visual review remains pending."
    )
  } else if (!identical(config$parity_status, "approved")) {
    paste(
      "Build passed data and rendering checks; numerical reference parity",
      "and manuscript-owner visual review remain pending."
    )
  } else if (isTRUE(revision$dirty)) {
    "Build passed checks but was produced from uncommitted figure code."
  } else if (!is_complete) {
    "Standalone panel passed; it is not a complete publication release."
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
    stable_panel_ids = panel_ids,
    panel_letters_are_assembly_only = TRUE,
    policy_concordance_is_not_independent_validation = TRUE,
    review_candidates_are_not_policy_recommendations = TRUE,
    missing_susdat_match_is_not_analytical_impossibility = TRUE
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
message(
  "Policy concordance output written to: ",
  normalizePath(output_dir, mustWork = TRUE)
)
