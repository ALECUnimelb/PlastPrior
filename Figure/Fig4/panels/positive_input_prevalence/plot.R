plot_priority_positive_input_prevalence <- function(source_data, config) {
  plot_data <- source_data$positive_input_prevalence
  component_order <- vapply(
    config$components, function(item) item$component, character(1)
  )
  plot_data$component <- factor(
    plot_data$component, levels = rev(component_order)
  )
  plot_data$priority_tier <- factor(
    plot_data$priority_tier, levels = priority_sensitivity_levels
  )
  palette <- priority_sensitivity_named_palette(config, "priority_palette")

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(
      x = positive_proportion, y = component, colour = priority_tier
    )
  ) +
    ggplot2::geom_line(
      ggplot2::aes(group = component), colour = "#C8CDD3", linewidth = 0.5
    ) +
    ggplot2::geom_point(size = 2.2) +
    ggplot2::scale_colour_manual(
      values = palette,
      labels = c(
        "Low priority" = "Low",
        "Moderate priority" = "Moderate",
        "High priority" = "High"
      ),
      drop = FALSE
    ) +
    ggplot2::scale_x_continuous(
      labels = scales::label_percent(accuracy = 1),
      limits = c(0, 1), breaks = seq(0, 1, by = 0.25),
      expand = ggplot2::expansion(add = c(0.015, 0.015))
    ) +
    ggplot2::labs(
      x = "Compounds with positive contribution",
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
      legend.justification = "left",
      legend.spacing.x = grid::unit(1.2, "mm")
    )
}
