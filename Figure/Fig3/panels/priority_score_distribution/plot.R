# This semantic panel inherits theme_classic(base_size = 8,
# base_family = "Arial") and delegates svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600) to the module build/export contract
# (assembled width_mm = 183; standalone dimensions are in figure.yml).

plot_priority_score_distribution <- function(panel_data, config, variant = "publication") {
  distribution <- panel_data$priority_distribution
  distribution$Priority_tier <- factor(
    distribution$Priority_tier,
    levels = priority_levels
  )
  priority_palette <- named_palette(config, "priority_palette")
  base_plot <- ggplot2::ggplot(
    distribution,
    ggplot2::aes(x = score_bin, y = compound_count, fill = Priority_tier)
  ) +
    ggplot2::geom_col(show.legend = TRUE, width = 0.82, colour = "white", linewidth = 0.15) +
    ggplot2::scale_fill_manual(
      values = priority_palette,
      breaks = c("Low priority", "Moderate priority", "High priority", "No data"),
      drop = FALSE
    ) +
    ggplot2::scale_x_continuous(
      breaks = seq(min(distribution$score_bin), max(distribution$score_bin), by = 2),
      expand = ggplot2::expansion(add = c(0.55, 0.55))
    ) +
    ggplot2::scale_y_continuous(
      labels = scales::comma,
      expand = ggplot2::expansion(mult = c(0, 0.12))
    ) +
    ggplot2::labs(
      x = "Priority score (1-point intervals)",
      y = "Number of compounds"
    ) +
    priority_landscape_theme() +
    ggplot2::theme(
      legend.position = "top",
      legend.justification = "left",
      legend.direction = "horizontal"
    ) +
    ggplot2::guides(fill = ggplot2::guide_legend(
      override.aes = list(
        fill = unname(priority_palette[c(
          "Low priority", "Moderate priority", "High priority", "No data"
        )])
      )
    ))

  total <- sum(distribution$compound_count)
  min_count <- if (identical(variant, "audit_all_values")) {
    1
  } else {
    max(
      as.numeric(config$display$priority_distribution_label_min_count),
      total * as.numeric(config$display$priority_distribution_label_min_fraction)
    )
  }
  labels <- stats::aggregate(compound_count ~ score_bin, distribution, sum)
  labels <- labels[labels$compound_count >= min_count, , drop = FALSE]
  base_plot + ggplot2::geom_text(
    data = labels,
    ggplot2::aes(x = score_bin, y = compound_count, label = scales::comma(compound_count)),
    inherit.aes = FALSE,
    vjust = -0.35, size = 2.05, colour = "#202830",
    check_overlap = TRUE
  )
}
