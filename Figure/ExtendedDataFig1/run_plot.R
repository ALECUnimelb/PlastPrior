#!/usr/bin/env Rscript

# Run script for manuscript Figure 2: Source Assembly and Database Overlap.
# Automatically locates the latest Result snapshot, extracts data, and produces figures.

script_directory <- function() {
  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 1L) {
    path_val <- sub("^--file=", "", file_arg[[1]])
    # R 4.6 on macOS may encode space as ~+~
    path_val <- gsub("~[+]~", " ", path_val)
    path_val <- gsub("~n~", "\n", path_val)
    return(dirname(normalizePath(path_val, mustWork = TRUE)))
  }
  # Fallback to current working directory
  getwd()
}

current_dir <- script_directory()
repo_root <- normalizePath(file.path(current_dir, "..", ".."), mustWork = TRUE)

shared_dir <- file.path(dirname(current_dir), "_shared")
for (helper in c("palette.R", "theme.R", "export.R", "validation.R")) {
  source(file.path(shared_dir, helper), encoding = "UTF-8")
}
source(file.path(current_dir, "snapshot_loader.R"), encoding = "UTF-8")
source(file.path(current_dir, "data.R"), encoding = "UTF-8")
source(file.path(current_dir, "export_data.R"), encoding = "UTF-8")
source(file.path(current_dir, "plot_sankey.R"), encoding = "UTF-8")
source(file.path(current_dir, "plot_upset.R"), encoding = "UTF-8")
source(file.path(current_dir, "assemble.R"), encoding = "UTF-8")

require_r_packages(c(
  "digest", "dplyr", "ggplot2", "jsonlite", "patchwork", "ragg", "readr",
  "scales", "stringr", "svglite", "systemfonts", "tibble", "tidyr", "tidyselect"
))

# Parse CLI arguments if provided
args <- commandArgs(trailingOnly = TRUE)
snapshot_override <- NULL
output_override <- NULL

index <- 1L
while (index <= length(args)) {
  if (args[[index]] == "--snapshot" && index < length(args)) {
    snapshot_override <- args[[index + 1L]]
    index <- index + 2L
  } else if (args[[index]] == "--output-dir" && index < length(args)) {
    output_override <- args[[index + 1L]]
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

# A failed/interrupted run must never leave an old success record in place.
run_manifest_path <- file.path(output_dir, "export", "run_manifest.json")
run_manifest <- list(
  schema_version = 1L,
  status = "in_progress",
  started_at_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  snapshot_name = basename(dirname(dirname(snapshot_path)))
)
write_json_utf8(run_manifest, run_manifest_path)

config <- jsonlite::fromJSON(file.path(current_dir, "figure.yml"), simplifyVector = FALSE)
snapshot <- load_snapshot(snapshot_path)

message("==> Reading snapshot tables...")
compounds <- readr::read_csv(
  snapshot$compounds_path,
  col_types = readr::cols(
    inchikey_std = readr::col_character(),
    keep_for_vega = readr::col_character(),
    qc_flags = readr::col_character(),
    .default = readr::col_character()
  ),
  show_col_types = FALSE,
  progress = FALSE
)
catalog <- read_source_catalog(snapshot)
attrition <- read_source_attrition(snapshot)

message("==> Preparing Sankey flow & UpSet overlap data...")
sankey <- prepare_sankey_source_data(snapshot, compounds, catalog, attrition, config)
overlap <- prepare_database_overlap(snapshot, compounds, catalog, attrition, config)
panel_exports <- prepare_panel_exports(sankey, overlap)

# Create output subdirectories
sankey_source_dir <- file.path(output_dir, "source_data", "identity_resolution_flow")
upset_source_dir <- file.path(output_dir, "source_data", "source_database_intersections")
audit_dir <- file.path(output_dir, "audit")
figures_out_dir <- file.path(output_dir, "figures")

dir.create(sankey_source_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(upset_source_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(audit_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(figures_out_dir, recursive = TRUE, showWarnings = FALSE)

readr::write_csv(sankey$aggregate, file.path(sankey_source_dir, "record_flow_aggregate.csv"), na = "")
readr::write_csv(sankey$edges, file.path(sankey_source_dir, "sankey_edges.csv"), na = "")
readr::write_csv(sankey$nodes, file.path(sankey_source_dir, "sankey_nodes.csv"), na = "")
readr::write_csv(sankey$summary, file.path(sankey_source_dir, "sankey_summary.csv"), na = "")
readr::write_csv(sankey$source_validation, file.path(sankey_source_dir, "source_record_validation.csv"), na = "")
readr::write_csv(overlap$membership, file.path(upset_source_dir, "database_membership.csv"), na = "")
readr::write_csv(overlap$set_sizes, file.path(upset_source_dir, "database_set_sizes.csv"), na = "")
readr::write_csv(overlap$intersections, file.path(upset_source_dir, "database_intersections_all.csv"), na = "")
readr::write_csv(overlap$selected, file.path(upset_source_dir, "database_intersections_displayed.csv"), na = "")
readr::write_csv(overlap$summary, file.path(upset_source_dir, "selection_summary.csv"), na = "")

message("==> Rendering panels...")
sankey_panel <- plot_identity_resolution_flow(sankey$edges, sankey$nodes, config)
upset_panel <- plot_source_database_intersections(overlap, config)

# Save layout audit tables
readr::write_csv(sankey_panel$label_layout, file.path(sankey_source_dir, "sankey_label_layout.csv"), na = "")
readr::write_csv(sankey_panel$connector_segments, file.path(sankey_source_dir, "sankey_connector_routes.csv"), na = "")
readr::write_csv(sankey_panel$connector_track_summary, file.path(sankey_source_dir, "sankey_connector_track_summary.csv"), na = "")
readr::write_csv(sankey_panel$label_collisions, file.path(audit_dir, "sankey_label_collisions.csv"), na = "")
readr::write_csv(sankey_panel$label_node_collisions, file.path(audit_dir, "sankey_label_node_collisions.csv"), na = "")
readr::write_csv(sankey_panel$connector_intersections, file.path(audit_dir, "sankey_connector_intersections.csv"), na = "")
readr::write_csv(sankey_panel$connector_node_collisions, file.path(audit_dir, "sankey_connector_node_collisions.csv"), na = "")
readr::write_csv(sankey_panel$connector_label_collisions, file.path(audit_dir, "sankey_connector_label_collisions.csv"), na = "")
readr::write_csv(sankey_panel$connector_orthogonality, file.path(audit_dir, "sankey_connector_orthogonality.csv"), na = "")
readr::write_csv(sankey_panel$connector_clearance_violations, file.path(audit_dir, "sankey_connector_clearance_violations.csv"), na = "")
readr::write_csv(sankey_panel$order_violations, file.path(audit_dir, "sankey_node_order_violations.csv"), na = "")

message("==> Exporting figures (PDF, PNG, SVG, TIFF)...")
dpi <- as.numeric(config$export$dpi)
formats <- c("svg", "pdf", "png", "tiff")

# 1. Export Sankey hero panel
export_figure(
  sankey_panel$plot,
  file.path(figures_out_dir, "figure_sankey_flow"),
  width_mm = as.numeric(config$export$width_mm),
  height_mm = as.numeric(config$sankey$panel_height_mm),
  dpi = dpi,
  formats = formats
)

# 2. Export UpSet panel
export_figure(
  upset_panel$plot,
  file.path(figures_out_dir, "figure_upset_overlap"),
  width_mm = as.numeric(config$export$width_mm),
  height_mm = as.numeric(config$upset$panel_height_mm),
  dpi = dpi,
  formats = formats
)

# 3. Export Assembled Composite Figure (Figure 2 in manuscript)
assembled <- assemble_source_assembly_and_overlap(
  sankey_panel$plot,
  upset_panel$plot
)
export_figure(
  assembled,
  file.path(figures_out_dir, "figure_composite_assembly_and_overlap"),
  width_mm = as.numeric(config$export$width_mm),
  height_mm = as.numeric(config$export$height_mm),
  dpi = dpi,
  formats = formats
)

# Save caption facts
sankey_facts <- stats::setNames(sankey$summary$value, sankey$summary$metric)
caption_facts <- list(
  source_records = unname(sankey_facts[["source_records"]]),
  resolved_records = unname(sankey_facts[["resolved_records"]]),
  unresolved_records = unname(sankey_facts[["unresolved_records"]]),
  unique_compounds = unname(sankey_facts[["unique_compounds"]]),
  collapsed_duplicate_records = unname(sankey_facts[["collapsed_duplicate_records"]]),
  qsar_eligible_compounds = unname(sankey_facts[["qsar_eligible_compounds"]]),
  registered_databases = nrow(overlap$set_sizes),
  displayed_exact_intersections = nrow(overlap$selected),
  intersection_rule = paste0(overlap$comparison, " ", overlap$threshold),
  displayed_compounds = overlap$displayed_compounds,
  displayed_coverage_percent = round(overlap$displayed_coverage, 3)
)
write_json_utf8(caption_facts, file.path(audit_dir, "caption_facts.json"))

# Publish the convenient tables only after all three figure exports succeed.
export_dir <- file.path(output_dir, "export")
write_panel_exports(panel_exports, export_dir)
run_manifest$status <- "success"
run_manifest$completed_at_utc <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
run_manifest$input_sha256 <- list(
  compounds = sha256_file(snapshot$compounds_path),
  audit = sha256_file(snapshot$audit_path),
  config = sha256_file(file.path(current_dir, "figure.yml"))
)
run_manifest$selection <- config$upset[c("min_intersection_size", "comparison", "max_intersections")]
run_manifest$database_columns <- overlap$set_sizes[, c("source_id", "display_label", "compact_column", "row_order", "set_size", "color")]
run_manifest$counts <- caption_facts
run_manifest$export_sha256 <- list(
  figure2a_sankey = sha256_file(file.path(export_dir, "figure2a_sankey.csv")),
  figure2b_upset = sha256_file(file.path(export_dir, "figure2b_upset.csv"))
)
write_json_utf8(run_manifest, run_manifest_path)

message("\n[SUCCESS] Successfully generated figures in: ", figures_out_dir)
message("  - figure_sankey_flow.(png|pdf|svg|tiff)")
message("  - figure_upset_overlap.(png|pdf|svg|tiff)")
message("  - figure_composite_assembly_and_overlap.(png|pdf|svg|tiff)")
message("  - Copy-ready CSV files: ", export_dir)
