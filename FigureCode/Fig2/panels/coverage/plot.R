plot_pbmt_coverage <- function(source_data, config, variant) {
  coverage <- source_data$coverage_summary
  metrics <- source_data$coverage_metrics
  assert_columns(
    coverage,
    c("dimension", "category", "count", "fraction"),
    "PBMT coverage summary"
  )
  dimension_levels <- rev(pbmt_dimension_levels)
  coverage$dimension <- factor(coverage$dimension, levels = dimension_levels)
  coverage$category <- factor(coverage$category, levels = pbmt_coverage_levels)
  coverage$category_index <- match(as.character(coverage$category), pbmt_coverage_levels)
  coverage <- coverage[order(coverage$dimension, coverage$category_index), , drop = FALSE]
  coverage$label_x <- ave(
    coverage$fraction,
    coverage$dimension,
    FUN = function(values) cumsum(values) - values / 2
  )
  min_fraction <- as.numeric(config$thresholds$coverage_label_min_fraction)
  coverage$small_nonzero <- coverage$count > 0 & coverage$fraction < min_fraction
  if (identical(variant, "audit_all_values")) {
    coverage$inside_label <- ifelse(
      coverage$count > 0 & !coverage$small_nonzero,
      paste0(
        scales::comma(coverage$count), "\n",
        scales::percent(coverage$fraction, accuracy = 0.1)
      ),
      ""
    )
  } else {
    coverage$inside_label <- ifelse(
      coverage$fraction >= min_fraction,
      scales::percent(coverage$fraction, accuracy = 0.1),
      ""
    )
  }
  coverage$label_colour <- ifelse(
    coverage$category %in% c("Independent only", "Shared"),
    "white", "#222222"
  )
  coverage$dimension_index <- as.numeric(coverage$dimension)
  coverage$callout_label <- ifelse(
    coverage$small_nonzero,
    if (identical(variant, "audit_all_values")) {
      paste0(
        scales::comma(coverage$count), "\n",
        scales::percent(coverage$fraction, accuracy = 0.1)
      )
    } else {
      scales::percent(coverage$fraction, accuracy = 0.1)
    },
    ""
  )
  small_labels <- coverage[coverage$small_nonzero, , drop = FALSE]
  small_labels$callout_x <- numeric(nrow(small_labels))
  small_labels$leader_start_y <- numeric(nrow(small_labels))
  small_labels$leader_end_y <- numeric(nrow(small_labels))
  small_labels$callout_y <- numeric(nrow(small_labels))
  small_labels$leader_colour <- character(nrow(small_labels))
  spread_callout_positions <- function(values, min_gap = 0.055) {
    if (length(values) <= 1L) {
      return(values)
    }
    value_order <- order(values)
    sorted_values <- values[value_order]
    positions <- sorted_values
    for (index in 2:length(positions)) {
      positions[[index]] <- max(
        positions[[index]], positions[[index - 1L]] + min_gap
      )
    }
    positions <- positions + mean(sorted_values) - mean(positions)
    if (min(positions) < 0.025) {
      positions <- positions + 0.025 - min(positions)
    }
    if (max(positions) > 0.975) {
      positions <- positions - max(positions) + 0.975
    }
    restored <- numeric(length(values))
    restored[value_order] <- positions
    restored
  }
  if (nrow(small_labels) > 0L) {
    small_labels$callout_x <- ave(
      small_labels$label_x,
      small_labels$dimension,
      FUN = spread_callout_positions
    )
    small_labels$leader_start_y <- small_labels$dimension_index + 0.28
    small_labels$leader_end_y <- small_labels$dimension_index + 0.38
    small_labels$callout_y <- small_labels$dimension_index + 0.46
  }
  population_values <- unique(metrics$population_total)
  if (length(population_values) != 1L) {
    stop("PBMT coverage has inconsistent population totals.", call. = FALSE)
  }
  palette <- pbmt_named_palette(config, "coverage_palette")
  if (nrow(small_labels) > 0L) {
    small_labels$leader_colour <- unname(
      palette[as.character(small_labels$category)]
    )
  }
  ggplot2::ggplot(
    coverage,
    ggplot2::aes(x = fraction, y = dimension, fill = category)
  ) +
    ggplot2::geom_col(
      width = 0.54, colour = "white", linewidth = 0.25,
      position = ggplot2::position_stack(reverse = TRUE)
    ) +
    ggplot2::geom_text(
      ggplot2::aes(x = label_x, label = inside_label, colour = label_colour),
      family = resolve_manuscript_font(),
      size = 2.2,
      lineheight = 0.9,
      fontface = "bold",
      show.legend = FALSE
    ) +
    ggplot2::geom_segment(
      data = small_labels,
      ggplot2::aes(
        x = label_x, xend = callout_x,
        y = leader_start_y, yend = leader_end_y,
        colour = leader_colour
      ),
      inherit.aes = FALSE,
      linewidth = 0.35,
      lineend = "round",
      show.legend = FALSE
    ) +
    ggplot2::geom_text(
      data = small_labels,
      ggplot2::aes(x = callout_x, y = callout_y, label = callout_label),
      inherit.aes = FALSE,
      family = resolve_manuscript_font(),
      colour = "#333333",
      size = 1.9,
      lineheight = 0.88,
      fontface = "bold",
      hjust = 0.5,
      vjust = 0.5
    ) +
    ggplot2::scale_fill_manual(
      values = palette, breaks = pbmt_coverage_levels, drop = FALSE
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_x_continuous(
      breaks = c(0, 0.25, 0.5, 0.75, 1),
      labels = scales::percent_format(accuracy = 1),
      limits = c(0, 1),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::scale_y_discrete(
      expand = ggplot2::expansion(add = c(0.30, 0.68))
    ) +
    ggplot2::labs(
      x = "Share of full inventory",
      y = NULL
    ) +
    pbmt_theme(base_size = 7) +
    ggplot2::theme(
      axis.line.y = ggplot2::element_blank(),
      axis.ticks.y = ggplot2::element_blank(),
      axis.text.y = ggplot2::element_text(face = "bold", size = 7),
      legend.position = "top",
      legend.direction = "horizontal",
      legend.justification = "left",
      legend.box.just = "left",
      plot.margin = ggplot2::margin(4, 6, 3, 8)
    ) +
    ggplot2::guides(fill = ggplot2::guide_legend(nrow = 1, byrow = TRUE))
}
