pbmt_prepare_severity_plot_data <- function(source_data, dimension_id, config, variant) {
  agreement <- source_data$agreement_band_summary
  metrics <- source_data$agreement_metrics
  agreement <- agreement[agreement$dimension_id == dimension_id, , drop = FALSE]
  metrics <- metrics[metrics$dimension_id == dimension_id, , drop = FALSE]
  if (nrow(agreement) != length(pbmt_agreement_levels) || nrow(metrics) != 1L) {
    stop("Agreement plot data are incomplete for ", dimension_id, ".", call. = FALSE)
  }
  agreement$agreement_band <- factor(
    agreement$agreement_band, levels = pbmt_agreement_levels
  )
  agreement <- agreement[order(agreement$agreement_band), , drop = FALSE]
  agreement$dimension_factor <- factor(agreement$dimension, levels = agreement$dimension[[1]])
  agreement$label_position <- cumsum(agreement$fraction_of_shared) -
    agreement$fraction_of_shared / 2
  label_min <- as.numeric(config$thresholds$severity_label_min_fraction)
  if (identical(variant, "audit_all_values")) {
    agreement$inside_label <- ifelse(
      agreement$count > 0,
      paste0(
        scales::comma(agreement$count), "\n",
        scales::percent(agreement$fraction_of_shared, accuracy = 0.1)
      ),
      ""
    )
  } else {
    agreement$inside_label <- ifelse(
      agreement$fraction_of_shared >= label_min,
      scales::percent(agreement$fraction_of_shared, accuracy = 1),
      ""
    )
  }
  agreement$label_colour <- ifelse(
    agreement$agreement_band %in% c("Exact", "Large (>1)"),
    "white", "#222222"
  )
  list(agreement = agreement, metrics = metrics)
}

plot_pbmt_agreement_severity <- function(source_data, dimension_id, config, variant) {
  plot_data <- pbmt_prepare_severity_plot_data(
    source_data, dimension_id, config, variant
  )
  agreement <- plot_data$agreement
  metrics <- plot_data$metrics
  palette <- pbmt_named_palette(config, "agreement_palette")
  dimension <- as.character(metrics$dimension[[1]])
  subtitle <- paste0(
    "Shared n = ", scales::comma(metrics$shared_n),
    "  |  mean |Δ| = ", scales::number(metrics$mean_absolute_difference, accuracy = 0.01)
  )
  ggplot2::ggplot(
    agreement,
    ggplot2::aes(x = fraction_of_shared, y = dimension_factor, fill = agreement_band)
  ) +
    ggplot2::geom_col(
      width = 0.55, colour = "white", linewidth = 0.25,
      position = ggplot2::position_stack(reverse = TRUE)
    ) +
    ggplot2::geom_text(
      ggplot2::aes(
        x = label_position, label = inside_label, colour = label_colour
      ),
      family = resolve_manuscript_font(),
      size = if (identical(variant, "audit_all_values")) 2.1 else 1.9,
      lineheight = 0.88,
      fontface = "bold",
      show.legend = FALSE
    ) +
    ggplot2::scale_fill_manual(
      values = palette,
      breaks = pbmt_agreement_levels,
      labels = c("Exact", "Near (≤0.5)", "Moderate (0.5–1)", "Large (>1)"),
      drop = FALSE
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_x_continuous(
      breaks = c(0, 0.25, 0.5, 0.75, 1),
      labels = scales::percent_format(accuracy = 1),
      limits = c(0, 1),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::labs(
      title = dimension,
      subtitle = subtitle,
      x = "Share of shared compounds",
      y = NULL
    ) +
    pbmt_theme(base_size = 6.2) +
    ggplot2::theme(
      axis.line.y = ggplot2::element_blank(),
      axis.ticks.y = ggplot2::element_blank(),
      axis.text.y = ggplot2::element_blank(),
      legend.position = if (identical(variant, "audit_all_values")) "top" else "none",
      legend.direction = "horizontal",
      legend.justification = "left",
      plot.title = ggplot2::element_text(face = "bold", size = 7.1),
      plot.subtitle = ggplot2::element_text(size = 5.7),
      plot.margin = ggplot2::margin(3, 4, 2, 5)
    )
}

pbmt_prepare_matrix_plot_data <- function(source_data, dimension_id, config, variant) {
  matrix <- source_data$score_pair_matrix
  matrix <- matrix[matrix$dimension_id == dimension_id, , drop = FALSE]
  expected_rows <- length(pbmt_plastchem_score_levels) *
    length(pbmt_computational_score_levels)
  if (nrow(matrix) != expected_rows || length(unique(matrix$shared_n)) != 1L) {
    stop("Score-pair matrix data are incomplete for ", dimension_id, ".", call. = FALSE)
  }
  matrix$plastchem_factor <- factor(
    pbmt_score_label(matrix$plastchem_score),
    levels = pbmt_score_label(pbmt_plastchem_score_levels)
  )
  matrix$computational_factor <- factor(
    pbmt_score_label(matrix$computational_score),
    levels = pbmt_score_label(pbmt_computational_score_levels)
  )
  if (identical(variant, "audit_all_values")) {
    matrix$count_label <- ifelse(matrix$count > 0, scales::comma(matrix$count), "")
  } else {
    label_min <- max(
      as.numeric(config$thresholds$matrix_label_min_count),
      max(matrix$count) * as.numeric(config$thresholds$matrix_label_min_max_fraction)
    )
    matrix$count_label <- ifelse(
      matrix$count >= label_min, scales::comma(matrix$count), ""
    )
  }
  matrix$label_colour <- ifelse(matrix$fraction_of_shared >= 0.18, "white", "#222222")
  matrix$exact_cell <- as.logical(matrix$exact_cell)
  matrix
}

plot_pbmt_score_matrix <- function(source_data, dimension_id, config, variant) {
  matrix <- pbmt_prepare_matrix_plot_data(source_data, dimension_id, config, variant)
  palette <- unlist(config$score_pair_palette, use.names = TRUE)
  fill_max <- max(matrix$fraction_of_shared)
  ggplot2::ggplot(
    matrix,
    ggplot2::aes(x = plastchem_factor, y = computational_factor)
  ) +
    ggplot2::geom_tile(
      ggplot2::aes(fill = fraction_of_shared),
      colour = "white", linewidth = 0.4
    ) +
    ggplot2::geom_tile(
      data = matrix[matrix$exact_cell, , drop = FALSE],
      fill = NA, colour = "#111111", linewidth = 0.65
    ) +
    ggplot2::geom_text(
      ggplot2::aes(label = count_label, colour = label_colour),
      family = resolve_manuscript_font(),
      fontface = "bold",
      size = if (identical(variant, "audit_all_values")) 2.05 else 1.85,
      show.legend = FALSE
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_fill_gradient(
      low = palette[["low"]], high = palette[["high"]],
      limits = c(0, fill_max),
      labels = scales::percent_format(accuracy = 1),
      oob = scales::squish,
      name = "Share of\nshared set"
    ) +
    ggplot2::scale_x_discrete(drop = FALSE) +
    ggplot2::scale_y_discrete(drop = FALSE) +
    ggplot2::coord_equal(expand = FALSE) +
    ggplot2::labs(
      title = if (identical(variant, "audit_all_values")) "Score-pair matrix" else NULL,
      subtitle = if (identical(variant, "audit_all_values")) {
        "Cell labels are true counts; outlined cells are exact matches."
      } else NULL,
      x = "PlastChem score",
      y = "Computational score"
    ) +
    pbmt_theme(base_size = 6.2) +
    ggplot2::theme(
      axis.line = ggplot2::element_blank(),
      axis.ticks = ggplot2::element_blank(),
      legend.position = if (identical(variant, "audit_all_values")) "right" else "none",
      legend.key.height = grid::unit(11, "mm"),
      plot.margin = ggplot2::margin(2, 4, 4, 5)
    )
}

assemble_pbmt_dimension <- function(
  severity_plot,
  matrix_plot,
  config,
  show_y_axis = TRUE
) {
  compact_severity <- severity_plot +
    ggplot2::labs(x = NULL) +
    ggplot2::theme(
      axis.title.x = ggplot2::element_blank(),
      plot.margin = ggplot2::margin(2, 4, 0, 5)
    )
  compact_matrix <- matrix_plot +
    ggplot2::theme(plot.margin = ggplot2::margin(0, 4, 4, 5))
  if (!isTRUE(show_y_axis)) {
    compact_matrix <- compact_matrix +
      ggplot2::theme(
        axis.title.y = ggplot2::element_blank(),
        axis.text.y = ggplot2::element_blank()
      )
  }

  capture_device <- NULL
  if (identical(unname(grDevices::dev.cur()), 1L)) {
    ragg::agg_capture(
      width = as.numeric(config$export$dimension_width_mm),
      height = as.numeric(config$export$dimension_height_mm),
      units = "mm",
      res = 72,
      background = "white"
    )
    capture_device <- grDevices::dev.cur()
    on.exit({
      open_devices <- grDevices::dev.list()
      if (!is.null(open_devices) && capture_device %in% open_devices) {
        grDevices::dev.off(capture_device)
      }
    }, add = TRUE)
  }
  severity_grob <- ggplot2::ggplotGrob(compact_severity)
  matrix_grob <- ggplot2::ggplotGrob(compact_matrix)
  severity_panel <- severity_grob$layout[
    severity_grob$layout$name == "panel", , drop = FALSE
  ]
  matrix_panel <- matrix_grob$layout[
    matrix_grob$layout$name == "panel", , drop = FALSE
  ]
  if (nrow(severity_panel) != 1L || nrow(matrix_panel) != 1L ||
      severity_panel$l != matrix_panel$l || severity_panel$r != matrix_panel$r ||
      length(severity_grob$widths) != length(matrix_grob$widths)) {
    stop(
      "PBMT dimension plots no longer expose compatible single-panel layouts.",
      call. = FALSE
    )
  }

  severity_grob$heights[severity_panel$t:severity_panel$b] <- grid::unit(
    as.numeric(config$layout$severity_panel_aspect), "null"
  )
  aligned <- rbind(severity_grob, matrix_grob, size = "max")
  aligned$respect <- isTRUE(matrix_grob$respect)
  patchwork::wrap_elements(full = aligned)
}
