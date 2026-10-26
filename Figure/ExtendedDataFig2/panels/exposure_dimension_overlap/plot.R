# Panel export inherits theme_classic(base_size = 7, base_family = "Arial") and
# delegates svglite::svglite("panel.svg"),
# grDevices::cairo_pdf("panel.pdf"), ragg::agg_png("panel.png", res = 600),
# and ragg::agg_tiff("panel.tiff", res = 600) to the module build at
# width_mm = 183.

exposure_dimension_names <- c(
  "Inventory presence",
  "Production / market",
  "Patents",
  "Literature",
  "Food-contact + biomonitoring"
)

exposure_score_columns <- list(
  "Inventory presence" = "Exposure_inventory_score",
  "Production / market" = "Exposure_production_score",
  "Patents" = "Exposure_patent_score",
  "Literature" = "Exposure_literature_score",
  "Food-contact + biomonitoring" = c(
    "Exposure_food_contact_score",
    "Exposure_human_biomonitoring_score"
  )
)

prepare_exposure_overlap <- function(compounds, source_data_dir) {
  require_r_packages(c("ggplot2", "patchwork", "readr", "scales"))
  required_scores <- unique(unlist(exposure_score_columns, use.names = FALSE))
  assert_columns(compounds, c("Inchikey_std", required_scores), "Snapshot compound table")

  numeric_scores <- list()
  for (column in required_scores) {
    allowed <- if (column %in% c(
      "Exposure_food_contact_score",
      "Exposure_human_biomonitoring_score"
    )) c(0, 1) else c(0, 0.5, 1, 2)
    numeric_scores[[column]] <- assert_discrete_numeric(
      compounds[[column]],
      allowed = allowed,
      column_name = column,
      allow_missing = FALSE
    )
  }

  membership <- data.frame(
    Inchikey_std = trimws(as.character(compounds$Inchikey_std)),
    stringsAsFactors = FALSE
  )
  for (dimension in exposure_dimension_names) {
    columns <- exposure_score_columns[[dimension]]
    score_frame <- as.data.frame(numeric_scores[columns], check.names = FALSE)
    membership[[dimension]] <- rowSums(score_frame > 0) > 0
  }
  membership$positive_indicator_count <- rowSums(
    membership[exposure_dimension_names]
  )
  membership$intersection_pattern <- apply(
    membership[exposure_dimension_names],
    1,
    function(row) {
      active <- exposure_dimension_names[as.logical(row)]
      if (length(active) == 0L) "None" else paste(active, collapse = " + ")
    }
  )

  combinations <- expand.grid(
    rep(list(c(FALSE, TRUE)), length(exposure_dimension_names)),
    KEEP.OUT.ATTRS = FALSE,
    stringsAsFactors = FALSE
  )
  names(combinations) <- exposure_dimension_names
  intersection_rows <- lapply(seq_len(nrow(combinations)), function(index) {
    combination <- as.logical(combinations[index, exposure_dimension_names])
    selector <- rep(TRUE, nrow(membership))
    for (position in seq_along(exposure_dimension_names)) {
      dimension <- exposure_dimension_names[[position]]
      selector <- selector & membership[[dimension]] == combination[[position]]
    }
    active <- exposure_dimension_names[combination]
    count <- sum(selector)
    data.frame(
      intersection_mask = paste0(as.integer(combination), collapse = ""),
      intersection_pattern = if (length(active) == 0L) "None" else paste(active, collapse = " + "),
      positive_indicator_count = length(active),
      as.list(setNames(combination, exposure_dimension_names)),
      compound_count = count,
      fraction_of_inventory = count / nrow(membership),
      displayed_in_figure = length(active) > 0L && count > 0L,
      check.names = FALSE,
      stringsAsFactors = FALSE
    )
  })
  intersections <- do.call(rbind, intersection_rows)
  displayed_indices <- which(intersections$displayed_in_figure)
  displayed_indices <- displayed_indices[order(
    -intersections$compound_count[displayed_indices],
    -intersections$positive_indicator_count[displayed_indices],
    intersections$intersection_mask[displayed_indices]
  )]
  intersections$display_rank <- NA_integer_
  intersections$display_rank[displayed_indices] <- seq_along(displayed_indices)
  intersections <- intersections[order(
    !intersections$displayed_in_figure,
    intersections$display_rank,
    -intersections$positive_indicator_count,
    intersections$intersection_mask,
    na.last = TRUE
  ), ]
  rownames(intersections) <- NULL
  displayed <- intersections[intersections$displayed_in_figure, ]
  displayed <- displayed[order(displayed$display_rank), ]
  if (nrow(displayed) == 0L) {
    stop("No positive Exposure-indicator intersections are available to plot.", call. = FALSE)
  }

  set_summary <- data.frame(
    dimension = exposure_dimension_names,
    dimension_order = seq_along(exposure_dimension_names),
    positive_count = vapply(
      exposure_dimension_names,
      function(dimension) sum(membership[[dimension]]),
      numeric(1)
    ),
    stringsAsFactors = FALSE
  )
  set_summary$no_positive_contribution_count <- nrow(membership) - set_summary$positive_count
  set_summary$positive_fraction <- set_summary$positive_count / nrow(membership)
  no_positive_count <- sum(membership$positive_indicator_count == 0L)
  positive_union_count <- nrow(membership) - no_positive_count
  all_five_count <- sum(
    membership$positive_indicator_count == length(exposure_dimension_names)
  )
  if (nrow(intersections) != 32L || sum(intersections$compound_count) != nrow(membership)) {
    stop("Exposure intersections do not conserve the full snapshot population.", call. = FALSE)
  }
  if (sum(displayed$compound_count) != positive_union_count) {
    stop("Displayed Exposure intersections do not conserve the positive union.", call. = FALSE)
  }

  dir.create(source_data_dir, recursive = TRUE, showWarnings = FALSE)
  readr::write_csv(membership, file.path(source_data_dir, "membership.csv"), na = "")
  readr::write_csv(set_summary, file.path(source_data_dir, "set_summary.csv"), na = "")
  readr::write_csv(intersections, file.path(source_data_dir, "intersection_summary.csv"), na = "")
  statistics <- list(
    population_total = nrow(membership),
    positive_union_count = positive_union_count,
    no_positive_indicator_count = no_positive_count,
    all_five_positive_count = all_five_count,
    complete_intersection_count = nrow(intersections),
    displayed_positive_intersection_count = nrow(displayed),
    complete_intersection_sum = sum(intersections$compound_count),
    displayed_positive_intersection_sum = sum(displayed$compound_count),
    excluded_rows = 0,
    membership_rule = "canonical Exposure score is greater than zero"
  )
  write_json_utf8(statistics, file.path(source_data_dir, "statistics.json"))

  font_family <- resolve_manuscript_font()
  row_lookup <- data.frame(
    dimension = exposure_dimension_names,
    display_label = c(
      "Inventory presence",
      "Production /\nmarket",
      "Patents",
      "Literature",
      "Food-contact +\nbiomonitoring"
    ),
    row_id = rev(seq_along(exposure_dimension_names)),
    stringsAsFactors = FALSE
  )
  set_summary$row_id <- row_lookup$row_id[
    match(set_summary$dimension, row_lookup$dimension)
  ]
  matrix_rows <- lapply(seq_along(exposure_dimension_names), function(index) {
    data.frame(
      intersection_id = displayed$display_rank,
      dimension = exposure_dimension_names[[index]],
      row_id = row_lookup$row_id[[index]],
      active = as.logical(displayed[[exposure_dimension_names[[index]]]]),
      stringsAsFactors = FALSE
    )
  })
  matrix_data <- do.call(rbind, matrix_rows)
  active_matrix <- matrix_data[matrix_data$active, ]
  line_data <- do.call(
    rbind,
    lapply(split(active_matrix, active_matrix$intersection_id), function(rows) {
      data.frame(
        intersection_id = rows$intersection_id[[1]],
        y_min = min(rows$row_id),
        y_max = max(rows$row_id)
      )
    })
  )
  displayed$bar_class <- ifelse(
    displayed$positive_indicator_count == length(exposure_dimension_names),
    "All five positive",
    "Other exact intersection"
  )
  max_count <- max(displayed$compound_count)
  bar_colors <- c(
    "Other exact intersection" = chemicalprio_palette$neutral_dark,
    "All five positive" = chemicalprio_palette$accent_red
  )

  bar_plot <- ggplot2::ggplot(
    displayed,
    ggplot2::aes(x = display_rank, y = compound_count)
  ) +
    ggplot2::geom_col(
      ggplot2::aes(fill = bar_class),
      width = 0.72,
      show.legend = FALSE
    ) +
    ggplot2::geom_text(
      ggplot2::aes(label = scales::comma(compound_count)),
      angle = 90,
      hjust = 0,
      nudge_y = max_count * 0.025,
      size = 1.75,
      family = font_family,
      colour = chemicalprio_palette$neutral_dark
    ) +
    ggplot2::scale_fill_manual(values = bar_colors) +
    ggplot2::scale_x_continuous(
      limits = c(0.35, nrow(displayed) + 0.65),
      expand = ggplot2::expansion(mult = 0)
    ) +
    ggplot2::scale_y_continuous(
      labels = scales::comma,
      limits = c(0, max_count * 1.28),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::labs(y = "Exact intersection size", x = NULL) +
    ggplot2::theme_minimal(base_size = 7, base_family = font_family) +
    ggplot2::theme(
      axis.text.x = ggplot2::element_blank(),
      axis.ticks.x = ggplot2::element_blank(),
      panel.grid.major.x = ggplot2::element_blank(),
      panel.grid.minor = ggplot2::element_blank(),
      panel.grid.major.y = ggplot2::element_line(
        linewidth = 0.25,
        colour = chemicalprio_palette$neutral_light
      ),
      plot.margin = ggplot2::margin(2, 5, 0, 1)
    )

  matrix_plot <- ggplot2::ggplot(
    matrix_data,
    ggplot2::aes(x = intersection_id, y = row_id)
  ) +
    ggplot2::geom_hline(
      yintercept = row_lookup$row_id,
      linewidth = 0.25,
      colour = chemicalprio_palette$neutral_faint
    ) +
    ggplot2::geom_segment(
      data = line_data,
      ggplot2::aes(
        x = intersection_id,
        xend = intersection_id,
        y = y_min,
        yend = y_max
      ),
      inherit.aes = FALSE,
      linewidth = 0.7,
      colour = chemicalprio_palette$neutral_mid,
      lineend = "round"
    ) +
    ggplot2::geom_point(size = 1.7, colour = chemicalprio_palette$neutral_light) +
    ggplot2::geom_point(
      data = active_matrix,
      ggplot2::aes(fill = dimension),
      shape = 21,
      size = 2.15,
      stroke = 0.3,
      colour = chemicalprio_palette$neutral_dark,
      show.legend = FALSE
    ) +
    ggplot2::scale_fill_manual(values = chemicalprio_palette$exposure) +
    ggplot2::scale_x_continuous(
      limits = c(0.35, nrow(displayed) + 0.65),
      breaks = seq_len(nrow(displayed)),
      expand = ggplot2::expansion(mult = 0)
    ) +
    ggplot2::scale_y_continuous(
      breaks = row_lookup$row_id,
      limits = c(0.5, length(exposure_dimension_names) + 0.5),
      expand = ggplot2::expansion(mult = 0)
    ) +
    ggplot2::labs(x = "Exact positive-indicator intersections", y = NULL) +
    ggplot2::theme_void(base_size = 7, base_family = font_family) +
    ggplot2::theme(
      axis.title.x = ggplot2::element_text(
        size = 7,
        colour = chemicalprio_palette$neutral_dark,
        margin = ggplot2::margin(t = 5)
      ),
      plot.margin = ggplot2::margin(0, 5, 4, 1)
    )

  set_plot <- ggplot2::ggplot(
    set_summary,
    ggplot2::aes(x = positive_count, y = row_id, fill = dimension)
  ) +
    ggplot2::geom_col(width = 0.62, orientation = "y", show.legend = FALSE) +
    ggplot2::geom_text(
      ggplot2::aes(label = scales::comma(positive_count)),
      hjust = -0.12,
      size = 2.05,
      family = font_family,
      colour = chemicalprio_palette$neutral_dark
    ) +
    ggplot2::scale_fill_manual(values = chemicalprio_palette$exposure) +
    ggplot2::scale_x_continuous(
      limits = c(0, max(set_summary$positive_count) * 1.55),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::scale_y_continuous(
      breaks = row_lookup$row_id,
      labels = row_lookup$display_label,
      limits = c(0.5, length(exposure_dimension_names) + 0.5),
      expand = ggplot2::expansion(mult = 0)
    ) +
    ggplot2::theme_void(base_size = 7, base_family = font_family) +
    ggplot2::theme(
      axis.text.y = ggplot2::element_text(
        size = 6.2,
        colour = chemicalprio_palette$neutral_dark,
        hjust = 1,
        lineheight = 0.92,
        margin = ggplot2::margin(r = 4)
      ),
      plot.margin = ggplot2::margin(0, 5, 4, 5)
    )

  header_plot <- ggplot2::ggplot() +
    ggplot2::annotate(
      "text",
      x = 0.5,
      y = 0.06,
      label = "Positive compounds\nper indicator",
      family = font_family,
      size = 2.2,
      colour = chemicalprio_palette$neutral_dark,
      fontface = "bold",
      lineheight = 0.95
    ) +
    ggplot2::xlim(0, 1) +
    ggplot2::ylim(0, 1) +
    ggplot2::theme_void()

  figure <- patchwork::wrap_plots(
    header = header_plot,
    intersections = bar_plot,
    sets = set_plot,
    matrix = matrix_plot,
    design = "
      AB
      CD
    ",
    widths = grid::unit(c(22, 1), c("mm", "null")),
    heights = c(0.59, 0.41)
  ) +
    patchwork::plot_annotation(
      theme = ggplot2::theme(
        text = ggplot2::element_text(family = font_family, colour = "#111820"),
        plot.title = ggplot2::element_text(face = "bold", size = 8, hjust = 0.5),
        plot.subtitle = ggplot2::element_text(
          size = 6.7,
          colour = chemicalprio_palette$neutral_mid,
          hjust = 0.5,
          margin = ggplot2::margin(t = 2, b = 3)
        ),
        plot.margin = ggplot2::margin(4, 4, 3, 4)
      )
    )
  list(plot = figure, statistics = statistics)
}
