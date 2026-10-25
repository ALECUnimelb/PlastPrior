plot_priority_leave_one_input_out <- function(source_data, config) {
  source <- source_data$leave_one_input_out
  component_order <- source$component
  plot_data <- rbind(
    data.frame(
      component = source$component,
      metric = "High-priority compounds retained",
      value = source$high_priority_retention,
      stringsAsFactors = FALSE
    ),
    data.frame(
      component = source$component,
      metric = "Rank correlation (Spearman rho)",
      value = source$rank_spearman,
      stringsAsFactors = FALSE
    )
  )
  plot_data$component <- factor(
    plot_data$component, levels = rev(component_order)
  )
  plot_data$metric <- factor(
    plot_data$metric,
    levels = c(
      "High-priority compounds retained",
      "Rank correlation (Spearman rho)"
    )
  )
  palette <- priority_sensitivity_named_palette(config, "metric_palette")

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(x = value, y = component, colour = metric)
  ) +
    ggplot2::geom_line(
      ggplot2::aes(group = component), colour = "#C8CDD3", linewidth = 0.5
    ) +
    ggplot2::geom_point(size = 2.2) +
    ggplot2::scale_colour_manual(values = palette, drop = FALSE) +
    ggplot2::scale_x_continuous(
      labels = scales::label_percent(accuracy = 1),
      limits = c(0, 1), breaks = seq(0, 1, by = 0.25),
      expand = ggplot2::expansion(add = c(0.015, 0.015))
    ) +
    ggplot2::labs(
      x = "Retention or rank correlation",
      y = NULL,
      colour = NULL
    ) +
    priority_sensitivity_theme() +
    ggplot2::theme(
      panel.grid.major.x = ggplot2::element_line(
        colour = "#E7E9ED", linewidth = 0.3
      ),
      legend.position = "top",
      legend.direction = "horizontal",
      legend.justification = "left"
    )
}
