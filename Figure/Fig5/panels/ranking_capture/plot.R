plot_policy_ranking_capture <- function(source_data, config) {
  plot_data <- source_data$ranking_capture_markers
  display_order <- c(
    "Integrated score", "Exposure only",
    "Integrated, inventory removed", "Hazard only"
  )
  plot_data$method <- factor(
    plot_data$method, levels = rev(display_order)
  )
  plot_data$label <- scales::percent(
    plot_data$captured_fraction, accuracy = 0.1
  )
  screened_fraction <- unique(plot_data$screened_fraction)
  if (length(screened_fraction) != 1L) {
    stop("Ranking markers must share one screening fraction.", call. = FALSE)
  }
  palette <- policy_named_palette(config, "method_palette")
  axis_maximum <- max(0.90, max(plot_data$captured_fraction) + 0.14)

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(y = method)
  ) +
    ggplot2::geom_vline(
      xintercept = screened_fraction,
      linetype = "dashed", colour = "#9AA5B1", linewidth = 0.45
    ) +
    ggplot2::geom_segment(
      ggplot2::aes(
        x = screened_fraction, xend = captured_fraction,
        yend = method
      ),
      colour = "#CAD1D8", linewidth = 1.1, lineend = "round"
    ) +
    ggplot2::geom_point(
      ggplot2::aes(x = captured_fraction, colour = method),
      size = 3.2
    ) +
    ggplot2::geom_text(
      ggplot2::aes(
        x = captured_fraction + 0.018,
        label = label, colour = method
      ),
      hjust = 0, size = 2.35, fontface = "bold",
      show.legend = FALSE
    ) +
    ggplot2::scale_colour_manual(values = palette, guide = "none") +
    ggplot2::scale_y_discrete(
      labels = c(
        "Integrated score" = "Integrated score",
        "Exposure only" = "Exposure only",
        "Integrated, inventory removed" = "Integrated\n(no inventory)",
        "Hazard only" = "Hazard only"
      )
    ) +
    ggplot2::scale_x_continuous(
      labels = scales::label_percent(accuracy = 1),
      limits = c(0, axis_maximum), breaks = seq(0, min(1,axis_maximum), by = 0.2),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::labs(
      x = "Strong-action chemicals captured",
      y = NULL
    ) +
    policy_theme() +
    ggplot2::theme(
      panel.grid.major.x = ggplot2::element_line(
        colour = "#E2E7EC", linewidth = 0.3
      ),
      panel.grid.major.y = ggplot2::element_blank(),
      axis.ticks.y = ggplot2::element_blank(),
      axis.line.y = ggplot2::element_blank(),
      plot.margin = ggplot2::margin(6, 11, 6, 8)
    )
}
