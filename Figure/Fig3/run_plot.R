#!/usr/bin/env Rscript

# Run script for manuscript Figure 3: Priority Landscape & Component Profiles
# Automatically locates the latest Result snapshot, extracts data, and produces figures.

script_directory <- function() {
  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 1L) {
    path_val <- sub("^--file=", "", file_arg[[1]])
    path_val <- gsub("~[+]~", " ", path_val)
    path_val <- gsub("~n~", "\n", path_val)
    return(dirname(normalizePath(path_val, mustWork = TRUE)))
  }
  getwd()
}

current_dir <- script_directory()
repo_root <- normalizePath(file.path(current_dir, "..", ".."), mustWork = TRUE)

shared_dir <- file.path(dirname(current_dir), "_shared")
for (helper in c("palette.R", "theme.R", "export.R", "validation.R", "priority_policy.R")) {
  source(file.path(shared_dir, helper), encoding = "UTF-8")
}
source(file.path(current_dir, "snapshot_loader.R"), encoding = "UTF-8")
source(file.path(current_dir, "style.R"), encoding = "UTF-8")
source(file.path(current_dir, "data.R"), encoding = "UTF-8")
source(file.path(current_dir, "export_data.R"), encoding = "UTF-8")

panel_ids <- c(
  "priority_score_distribution",
  "regulatory_context_inset",
  "hazard_exposure_landscape",
  "score_decomposition",
  "hazard_component_profiles",
  "exposure_component_profiles"
)

for (panel_id in panel_ids) {
  source(file.path(current_dir, "panels", panel_id, "data.R"), encoding = "UTF-8")
  source(file.path(current_dir, "panels", panel_id, "plot.R"), encoding = "UTF-8")
}
source(file.path(current_dir, "assemble.R"), encoding = "UTF-8")

require_r_packages(c(
  "digest", "dplyr", "ggplot2", "jsonlite", "patchwork", "ragg",
  "readr", "scales", "svglite", "systemfonts", "tidyselect"
))

# Parse CLI arguments if provided
args <- commandArgs(trailingOnly = TRUE)
snapshot_override <- NULL
output_override <- NULL
variant <- "publication"

index <- 1L
while (index <= length(args)) {
  if (args[[index]] == "--snapshot" && index < length(args)) {
    snapshot_override <- args[[index + 1L]]
    index <- index + 2L
  } else if (args[[index]] == "--output-dir" && index < length(args)) {
    output_override <- args[[index + 1L]]
    index <- index + 2L
  } else if (args[[index]] == "--variant" && index < length(args)) {
    variant <- args[[index + 1L]]
    index <- index + 2L
  } else {
    index <- index + 1L
  }
}

snapshot_path <- if (!is.null(snapshot_override)) {
  normalizePath(snapshot_override, mustWork = TRUE)
} else {
  find_latest_result_snapshot(repo_root)
}

output_dir <- if (!is.null(output_override)) {
  output_override
} else {
  file.path(dirname(dirname(snapshot_path)), "Figures", basename(current_dir))
}

message("==> Using Analysis Snapshot: ", snapshot_path)
message("==> Output Directory: ", output_dir)

export_dir <- file.path(output_dir, "export")
run_manifest_path <- file.path(export_dir, "run_manifest.json")
run_manifest <- list(
  schema_version = 1L, status = "in_progress", variant = variant,
  started_at_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  snapshot_name = basename(dirname(dirname(snapshot_path)))
)
write_json_utf8(run_manifest, run_manifest_path)
if (!variant %in% c("publication", "audit_all_values")) stop("Unknown variant.")

config <- jsonlite::fromJSON(file.path(current_dir, "figure.yml"), simplifyVector = FALSE)
snapshot <- load_priority_snapshot(snapshot_path)

message("==> Reading priority landscape compound data...")
config <- priority_config_for_snapshot(snapshot, config)
compounds <- read_priority_landscape_input(snapshot, config)
metadata <- priority_landscape_metadata(compounds)

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
    prepare = function() prepare_hazard_exposure_landscape(compounds, metadata, config),
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

prepared <- list()
panel_plots <- list()
panel_exports <- character()

dpi <- as.numeric(config$export$dpi)
formats <- c("svg", "pdf", "png", "tiff")

message("==> Generating individual panel plots and source data...")
for (panel_id in panel_ids) {
  prepared[[panel_id]] <- specifications[[panel_id]]$prepare()
  source_dir <- file.path(output_dir, "source_data", panel_id)
  dir.create(source_dir, recursive = TRUE, showWarnings = FALSE)
  for (table_name in names(prepared[[panel_id]]$source_data)) {
    readr::write_csv(
      prepared[[panel_id]]$source_data[[table_name]],
      file.path(source_dir, paste0(table_name, ".csv")),
      na = ""
    )
  }
  
  audit_panels_dir <- file.path(output_dir, "audit", "panels")
  dir.create(audit_panels_dir, recursive = TRUE, showWarnings = FALSE)
  write_json_utf8(
    prepared[[panel_id]]$statistics,
    file.path(audit_panels_dir, paste0(panel_id, ".json"))
  )
  
  panel_plots[[panel_id]] <- specifications[[panel_id]]$plot(
    prepared[[panel_id]]$source_data,
    config,
    variant
  )
  
  panel <- panel_config(config, panel_id)
  output_stem <- if (identical(variant, "publication")) {
    panel_id
  } else {
    paste0(panel_id, "_audit_all_values")
  }
  
  export_figure(
    panel_plots[[panel_id]],
    file.path(output_dir, "panels", panel_id, output_stem),
    width_mm = as.numeric(panel$width_mm),
    height_mm = as.numeric(panel$height_mm),
    dpi = dpi,
    formats = formats
  )
}

portable_tables <- prepare_priority_exports(prepared, config, variant)
message("==> Assembling final composite figure (Fig. 3 in manuscript)...")
assembled <- assemble_priority_landscape(panel_plots, config)

figures_out_dir <- file.path(output_dir, "figures")
dir.create(figures_out_dir, recursive = TRUE, showWarnings = FALSE)

export_figure(
  assembled,
  file.path(figures_out_dir, "figure_priority_landscape"),
  width_mm = as.numeric(config$export$width_mm),
  height_mm = as.numeric(config$export$height_mm),
  dpi = dpi,
  formats = formats
)

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
write_json_utf8(caption_facts, file.path(output_dir, "audit", "caption_facts.json"))

# Publish copy-ready data only after every figure has been exported.
write_priority_exports(portable_tables, export_dir)
run_manifest$status <- "success"
run_manifest$completed_at_utc <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
run_manifest$input_sha256 <- list(
  compounds = sha256_file(snapshot$compounds_path), audit = sha256_file(snapshot$audit_path),
  config = sha256_file(file.path(current_dir, "figure.yml"))
)
run_manifest$thresholds <- config$thresholds
run_manifest$display <- config$display
run_manifest$counts <- caption_facts
run_manifest$export_sha256 <- lapply(names(portable_tables), function(name) {
  sha256_file(file.path(export_dir, paste0(name, ".csv")))
})
names(run_manifest$export_sha256) <- names(portable_tables)
write_json_utf8(run_manifest, run_manifest_path)

message("\n[SUCCESS] Successfully generated figures in: ", figures_out_dir)
message("  - figure_priority_landscape.(png|pdf|svg|tiff)")
message("  - Six independent CSV files: ", export_dir)
