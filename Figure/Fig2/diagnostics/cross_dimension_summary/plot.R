plot_pbmt_cross_dimension_summary <- function(source_data, config, variant) {
  agreement <- source_data$agreement_band_summary
  metrics <- source_data$agreement_metrics
  dimension_levels <- rev(pbmt_dimension_levels)
  agreement$dimension <- factor(agreement$dimension, levels = dimension_levels)
  agreement$agreement_band <- factor(
    agreement$agreement_band, levels = pbmt_agreement_levels
  )
  agreement$band_index <- match(as.character(agreement$agreement_band), pbmt_agreement_levels)
  agreement <- agreement[order(agreement$dimension, agreement$band_index), , drop = FALSE]
  agreement$label_x <- ave(
    agreement$fraction_of_shared,
    agreement$dimension,
    FUN = function(values) cumsum(values) - values / 2
  )
  agreement$inside_label <- ifelse(
    agreement$count > 0,
    paste0(
      scales::comma(agreement$count), "\n",
      scales::percent(agreement$fraction_of_shared, accuracy = 0.1)
    ),
    ""
  )
  agreement$label_colour <- ifelse(
    agreement$agreement_band %in% c("Exact", "Large (>1)"), "white", "#222222"
  )
  metrics$dimension <- factor(metrics$dimension, levels = dimension_levels)
  metrics$metric_label <- paste0(
    "n = ", scales::comma(metrics$shared_n),
    "  |  mean |Δ| ", scales::number(metrics$mean_absolute_difference, accuracy = 0.01),
    "  |  comp. > PC ", scales::comma(metrics$computational_higher_count),
    "  |  PC > comp. ", scales::comma(metrics$plastchem_higher_count)
  )
  palette <- pbmt_named_palette(config, "agreement_palette")
  ggplot2::ggplot(
    agreement,
    ggplot2::aes(x = fraction_of_shared, y = dimension, fill = agreement_band)
  ) +
    ggplot2::geom_col(
      width = 0.62, colour = "white", linewidth = 0.25,
      position = ggplot2::position_stack(reverse = TRUE)
    ) +
    ggplot2::geom_text(
      ggplot2::aes(x = label_x, label = inside_label, colour = label_colour),
      family = resolve_manuscript_font(), size = 2.15, lineheight = 0.88,
      fontface = "bold", show.legend = FALSE
    ) +
    ggplot2::geom_vline(xintercept = 1, linewidth = 0.3, colour = "#B8B8B8") +
    ggplot2::geom_text(
      data = metrics,
      ggplot2::aes(x = 1.025, y = dimension, label = metric_label),
      inherit.aes = FALSE,
      family = resolve_manuscript_font(), colour = "#333333",
      size = 2.05, hjust = 0
    ) +
    ggplot2::scale_fill_manual(
      values = palette,
      breaks = pbmt_agreement_levels,
      labels = c("Exact", "Near non-exact (≤0.5)", "Moderate (0.5–1)", "Large (>1)"),
      drop = FALSE
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_x_continuous(
      breaks = c(0, 0.25, 0.5, 0.75, 1),
      labels = scales::percent_format(accuracy = 1),
      limits = c(0, 1.76),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::labs(
      title = "Agreement is moderate and dimension-dependent",
      subtitle = paste0(
        "Bars partition every shared pair by absolute score difference; ",
        "right text reports n, mean absolute difference and direction."
      ),
      x = "Share of shared compounds", y = NULL
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
      plot.margin = ggplot2::margin(4, 6, 4, 8)
    ) +
    ggplot2::guides(fill = ggplot2::guide_legend(nrow = 1, byrow = TRUE))
}

