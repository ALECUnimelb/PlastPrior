# Portable, panel-local source tables. All statistics come from data.R.
prepare_panel_exports <- function(sankey, overlap) {
  nodes <- sankey$nodes
  if (anyDuplicated(nodes$node_id)) stop("Duplicate Sankey node IDs.", call. = FALSE)
  a <- sankey$edges
  for (side in c("source", "target")) {
    index <- match(a[[paste0(side, "_id")]], nodes$node_id)
    if (anyNA(index)) stop("Sankey edge references a missing node.", call. = FALSE)
    for (field in c("display_label", "layer", "node_order", "node_color")) {
      a[[paste0(side, "_", field)]] <- nodes[[field]][index]
    }
  }

  b <- overlap$intersections
  b$display_rank <- match(b$database_pattern, overlap$selected$database_pattern)
  b$displayed <- as.integer(!is.na(b$display_rank))
  b <- b[, c("intersection_rank", "database_pattern", "database_count",
             "compound_count", "displayed", "display_rank", overlap$compact_columns)]
  if (sum(b$compound_count) != nrow(overlap$membership)) {
    stop("Exported intersections do not conserve the compound population.", call. = FALSE)
  }
  # Include EVERY intersection: the displayed subset alone undercounts set sizes.
  for (i in seq_along(overlap$compact_columns)) {
    column <- overlap$compact_columns[[i]]
    if (anyNA(b[[column]]) || any(!b[[column]] %in% c(0L, 1L))) {
      stop("Invalid source membership in export: ", column, call. = FALSE)
    }
    total <- sum(b$compound_count * b[[column]])
    if (total != overlap$set_sizes$set_size[[i]]) {
      stop("Exported database total disagrees with plot: ", column, call. = FALSE)
    }
  }
  if (sum(b$compound_count[b$displayed == 1L]) != overlap$displayed_compounds) {
    stop("Exported displayed intersections disagree with plot.", call. = FALSE)
  }
  list(a = a, b = b)
}

write_panel_exports <- function(tables, export_dir) {
  dir.create(export_dir, recursive = TRUE, showWarnings = FALSE)
  # UTF-8 BOM allows Excel on macOS/Windows to recognize non-ASCII labels.
  readr::write_excel_csv(tables$a, file.path(export_dir, "figure2a_sankey.csv"), na = "")
  readr::write_excel_csv(tables$b, file.path(export_dir, "figure2b_upset.csv"), na = "")
}
