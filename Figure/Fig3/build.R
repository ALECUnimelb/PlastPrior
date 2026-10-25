#!/usr/bin/env Rscript

# Modular publication contract: theme_classic(base_size = 8,
# base_family = "Arial") is supplied by style.R; editable SVG/PDF and 600-dpi
# raster output are delegated to _shared/export.R via svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600). The assembled figure is width_mm = 183 and
# height_mm = 215; standalone panel dimensions come from figure.yml.

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
source(file.path(shared_dir, "priority_policy.R"), encoding = "UTF-8")
source(file.path(module_dir, "style.R"), encoding = "UTF-8")
source(file.path(module_dir, "data.R"), encoding = "UTF-8")

panel_ids <- c(
  "priority_score_distribution",
  "regulatory_context_inset",
  "hazard_exposure_landscape",
  "score_decomposition",
  "hazard_component_profiles",
  "exposure_component_profiles"
)
for (panel_id in panel_ids) {
  source(
    file.path(module_dir, "panels", panel_id, "data.R"),
    encoding = "UTF-8"
  )
  source(
    file.path(module_dir, "panels", panel_id, "plot.R"),
    encoding = "UTF-8"
  )
}
source(file.path(module_dir, "assemble.R"), encoding = "UTF-8")

require_r_packages(c(
  "digest", "dplyr", "ggplot2", "jsonlite", "patchwork", "ragg",
  "readr", "scales", "svglite", "systemfonts", "tidyselect"
))
arguments <- parse_arguments(commandArgs(trailingOnly = TRUE))
if (!(arguments$panel %in% c("all", panel_ids))) {
  stop(
    "Unknown --panel value: ", arguments$panel,
    ". Valid values: all, ", paste(panel_ids, collapse = ", "),
    call. = FALSE
  )
}
if (!(arguments$variant %in% c("publication", "audit_all_values"))) {
  stop("--variant must be publication or audit_all_values.", call. = FALSE)
}

config <- jsonlite::fromJSON(
  file.path(module_dir, "figure.yml"),
  simplifyVector = FALSE
)
if (!identical(config$module_id, "priority_landscape") ||
    !identical(tolower(config$backend), "r")) {
  stop("figure.yml module_id or backend does not match this R module.", call. = FALSE)
}
configured_panel_ids <- vapply(
  config$panels,
  function(panel) panel$panel_id,
  character(1)
)
if (!identical(configured_panel_ids, panel_ids)) {
  stop("figure.yml panel order or IDs disagree with build.R.", call. = FALSE)
}

snapshot <- validate_analysis_snapshot_r(
  arguments$snapshot,
  required_columns = "Inchikey_std"
)
config <- priority_config_for_snapshot(snapshot, config)
compounds <- read_priority_landscape_input(snapshot, config)
metadata <- priority_landscape_metadata(compounds)

output_dir <- normalizePath(arguments$output_dir, mustWork = FALSE)
assert_output_directory_is_new(output_dir)
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

specifications <- list(
  priority_score_distribution = list(
    prepare = function() prepare_priority_score_distribution(compounds, metadata),
    plot = plot_priority_score_distribution
  ),
  regulatory_context_inset = list(
    prepare = function() prepare_regulatory_context_inset(compounds),
    plot = plot_regulatory_context_inset
  ),
  hazard_exposure_landscape = list(
    prepare = function() prepare_hazard_exposure_landscape(
      compounds, metadata, config
    ),
    plot = plot_hazard_exposure_landscape
  ),
  score_decomposition = list(
    prepare = function() prepare_score_decomposition(compounds),
    plot = plot_score_decomposition
  ),
  hazard_component_profiles = list(
    prepare = function() prepare_hazard_component_profiles(compounds),
    plot = plot_hazard_component_profiles
  ),
  exposure_component_profiles = list(
    prepare = function() prepare_exposure_component_profiles(compounds, metadata),
    plot = plot_exposure_component_profiles
  )
)
selected_ids <- if (identical(arguments$panel, "all")) panel_ids else arguments$panel
prepared <- list()
panel_plots <- list()
panel_exports <- character()

for (panel_id in selected_ids) {
  prepared[[panel_id]] <- specifications[[panel_id]]$prepare()
  source_dir <- file.path(staging_dir, "source_data", panel_id)
  dir.create(source_dir, recursive = TRUE, showWarnings = FALSE)
  for (table_name in names(prepared[[panel_id]]$source_data)) {
    readr::write_csv(
      prepared[[panel_id]]$source_data[[table_name]],
      file.path(source_dir, paste0(table_name, ".csv")),
      na = ""
    )
  }
  write_json_utf8(
    prepared[[panel_id]]$statistics,
    file.path(staging_dir, "audit", "panels", paste0(panel_id, ".json"))
  )
  panel_plots[[panel_id]] <- specifications[[panel_id]]$plot(
    prepared[[panel_id]]$source_data,
    config,
    arguments$variant
  )
  panel <- panel_config(config, panel_id)
  output_stem <- if (identical(arguments$variant, "publication")) {
    panel_id
  } else {
    paste0(panel_id, "_audit_all_values")
  }
  panel_exports <- c(
    panel_exports,
    export_figure(
      panel_plots[[panel_id]],
      file.path(staging_dir, "panels", panel_id, output_stem),
      width_mm = as.numeric(panel$width_mm),
      height_mm = as.numeric(panel$height_mm),
      dpi = as.numeric(config$export$dpi),
      formats = arguments$formats
    )
  )
}

figure_exports <- character()
if (identical(arguments$panel, "all") && identical(arguments$variant, "publication")) {
  assembled <- assemble_priority_landscape(panel_plots, config)
  figure_exports <- export_figure(
    assembled,
    file.path(staging_dir, "figure", "priority_landscape"),
    width_mm = as.numeric(config$export$width_mm),
    height_mm = as.numeric(config$export$height_mm),
    dpi = as.numeric(config$export$dpi),
    formats = arguments$formats
  )
}

caption_facts <- list(
  priority_tier_policy_version = config$priority_tier_policy_version,
  component_gates = list(moderate = config$thresholds$moderate_component_min,
                         high = config$thresholds$high_component_min),
  population_total = metadata$population_full,
  priority_score = list(
    minimum = metadata$priority_score_min,
    median = metadata$priority_score_median,
    maximum = metadata$priority_score_max,
    tier_counts = metadata$priority_tier_counts
  ),
  hazard_score_maximum = metadata$hazard_score_max,
  exposure_score_maximum = metadata$exposure_score_max,
  regulatory_context_is_score_input = FALSE,
  human_biomonitoring_positive = metadata$human_biomonitoring_positive,
  food_contact_positive = metadata$food_contact_positive
)
write_json_utf8(caption_facts, file.path(staging_dir, "audit", "caption_facts.json"))

revision <- git_revision(repo_root)
is_complete_publication <- identical(arguments$panel, "all") &&
  identical(arguments$variant, "publication")
qa <- list(
  passed = TRUE,
  release_eligible = (
    is_complete_publication &&
      isFALSE(revision$dirty) &&
      identical(config$parity_status, "approved")
  ),
  checks = list(
    snapshot_hashes_verified = TRUE,
    snapshot_csv_sqlite_identity_verified = TRUE,
    unique_compound_identity = !anyDuplicated(compounds$Inchikey_std),
    priority_score_reconstructed = TRUE,
    priority_tiers_reconstructed = TRUE,
    exposure_components_recomputed = TRUE,
    formal_policies_verified = TRUE,
    excluded_rows = 0,
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
  module_dir,
  pattern = "\\.(R|yml|md)$",
  recursive = TRUE,
  full.names = TRUE
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
      dplyr = as.character(utils::packageVersion("dplyr")),
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
    excluded_rows = 0,
    parity_status = config$parity_status,
    stable_panel_ids = panel_ids,
    panel_letters_are_assembly_only = TRUE,
    regulatory_context_is_score_input = FALSE,
    raw_hazard_exposure_pairs_preserved = TRUE
  ),
  key_results = caption_facts,
  panel_statistics = lapply(prepared, function(panel) panel$statistics),
  code = code_records,
  generated_files = relative_file_records(staging_dir, exclude = manifest_path),
  qa = qa
)
write_json_utf8(manifest, manifest_path)

if (!file.rename(staging_dir, output_dir)) {
  stop("Could not atomically publish the completed figure output directory.", call. = FALSE)
}
completed <- TRUE
message("Priority landscape output written to: ", normalizePath(output_dir, mustWork = TRUE))
