# Panel export inherits theme_classic(base_size = 7, base_family = "Arial") and
# delegates svglite::svglite("panel.svg"),
# grDevices::cairo_pdf("panel.pdf"), ragg::agg_png("panel.png", res = 600),
# and ragg::agg_tiff("panel.tiff", res = 600) to the module build at
# width_mm = 140.

hazard_dimension_names <- c(
  "Persistence",
  "Bioaccumulation",
  "Mobility",
  "Toxicity"
)

hazard_score_columns <- setNames(
  paste0(hazard_dimension_names, "_score"),
  hazard_dimension_names
)

prepare_hazard_overlap <- function(compounds, source_data_dir) {
  require_r_packages(c("ggplot2", "ggVennDiagram", "readr", "scales"))
  assert_columns(
    compounds,
    c("Inchikey_std", unname(hazard_score_columns)),
    "Snapshot compound table"
  )
  membership <- data.frame(
    Inchikey_std = trimws(as.character(compounds$Inchikey_std)),
    stringsAsFactors = FALSE
  )
  score_integrity <- list()
  for (dimension in hazard_dimension_names) {
    column <- hazard_score_columns[[dimension]]
    numeric_score <- assert_discrete_numeric(
      compounds[[column]],
      allowed = c(0, 0.25, 0.5, 1, 2),
      column_name = column,
      allow_missing = TRUE
    )
    membership[[dimension]] <- !is.na(numeric_score)
    score_integrity[[dimension]] <- list(
      score_column = column,
      usable_score_count = sum(!is.na(numeric_score)),
      supported_zero_count = sum(numeric_score == 0, na.rm = TRUE),
      score_levels = sort(unique(numeric_score[!is.na(numeric_score)]))
    )
  }
  membership$effective_dimension_count <- rowSums(
    membership[hazard_dimension_names]
  )
  membership$intersection_pattern <- apply(
    membership[hazard_dimension_names],
    1,
    function(row) {
      active <- hazard_dimension_names[as.logical(row)]
      if (length(active) == 0L) "None" else paste(active, collapse = " + ")
    }
  )

  combinations <- expand.grid(
    rep(list(c(FALSE, TRUE)), length(hazard_dimension_names)),
    KEEP.OUT.ATTRS = FALSE,
    stringsAsFactors = FALSE
  )
  names(combinations) <- hazard_dimension_names
  intersection_rows <- lapply(seq_len(nrow(combinations)), function(index) {
    combination <- as.logical(combinations[index, hazard_dimension_names])
    selector <- rep(TRUE, nrow(membership))
    for (position in seq_along(hazard_dimension_names)) {
      dimension <- hazard_dimension_names[[position]]
      selector <- selector & membership[[dimension]] == combination[[position]]
    }
    active <- hazard_dimension_names[combination]
    data.frame(
      intersection_mask = paste0(as.integer(combination), collapse = ""),
      intersection_pattern = if (length(active) == 0L) "None" else paste(active, collapse = " + "),
      effective_dimension_count = length(active),
      as.list(setNames(combination, hazard_dimension_names)),
      compound_count = sum(selector),
      fraction_of_inventory = sum(selector) / nrow(membership),
      check.names = FALSE,
      stringsAsFactors = FALSE
    )
  })
  intersections <- do.call(rbind, intersection_rows)
  intersections <- intersections[
    order(-intersections$effective_dimension_count, intersections$intersection_mask),
  ]
  rownames(intersections) <- NULL
  set_summary <- data.frame(
    dimension = hazard_dimension_names,
    dimension_order = seq_along(hazard_dimension_names),
    compound_count = vapply(
      hazard_dimension_names,
      function(dimension) sum(membership[[dimension]]),
      numeric(1)
    ),
    stringsAsFactors = FALSE
  )
  set_summary$fraction_of_inventory <- set_summary$compound_count / nrow(membership)
  none_count <- sum(membership$effective_dimension_count == 0L)
  all_four_count <- sum(membership$effective_dimension_count == length(hazard_dimension_names))
  if (nrow(intersections) != 16L || sum(intersections$compound_count) != nrow(membership)) {
    stop("Hazard intersections do not conserve the full snapshot population.", call. = FALSE)
  }

  dir.create(source_data_dir, recursive = TRUE, showWarnings = FALSE)
  readr::write_csv(membership, file.path(source_data_dir, "membership.csv"), na = "")
  readr::write_csv(set_summary, file.path(source_data_dir, "set_summary.csv"), na = "")
  readr::write_csv(intersections, file.path(source_data_dir, "intersection_summary.csv"), na = "")
  statistics <- list(
    population_total = nrow(membership),
    none_count = none_count,
    all_four_count = all_four_count,
    intersection_count = nrow(intersections),
    intersection_sum = sum(intersections$compound_count),
    excluded_rows = 0,
    membership_rule = "final canonical PBMT score is non-missing",
    score_integrity = score_integrity
  )
  write_json_utf8(statistics, file.path(source_data_dir, "statistics.json"))

  venn_sets <- lapply(
    hazard_dimension_names,
    function(dimension) membership$Inchikey_std[membership[[dimension]]]
  )
  names(venn_sets) <- hazard_dimension_names
  figure <- ggVennDiagram::ggVennDiagram(
    venn_sets,
    label = "count",
    label_geom = "text",
    label_size = 3.0,
    set_color = unname(chemicalprio_palette$hazard[hazard_dimension_names]),
    set_size = 3.0,
    edge_size = 0.65
  )
  figure$coordinates$clip <- "off"
  figure <- figure +
    ggplot2::scale_fill_gradient(
      low = chemicalprio_palette$neutral_faint,
      high = chemicalprio_palette$accent_red,
      labels = scales::comma
    ) +
    ggplot2::labs(
      fill = "Compounds"
    ) +
    ggplot2::theme_void(base_size = 7, base_family = resolve_manuscript_font()) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(
        face = "bold",
        size = 8,
        colour = chemicalprio_palette$neutral_dark,
        hjust = 0.5
      ),
      plot.subtitle = ggplot2::element_text(
        size = 6.7,
        colour = chemicalprio_palette$neutral_mid,
        hjust = 0.5,
        margin = ggplot2::margin(t = 2, b = 2)
      ),
      legend.position = "right",
      legend.title = ggplot2::element_text(size = 6.5),
      legend.text = ggplot2::element_text(size = 6),
      plot.margin = ggplot2::margin(5, 12, 5, 12)
    )
  list(plot = figure, statistics = statistics)
}
