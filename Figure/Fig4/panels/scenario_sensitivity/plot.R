plot_priority_scenario_sensitivity <- function(source_data, config) {
  source <- source_data$scenario_sensitivity
  scenario_order <- source$scenario
  plot_data <- rbind(
    data.frame(
      scenario = source$scenario,
      metric = "Rank rho",
      value = source$rank_spearman,
      stringsAsFactors = FALSE
    ),
    data.frame(
      scenario = source$scenario,
      metric = "Tier agreement",
      value = source$tier_agreement,
      stringsAsFactors = FALSE
    ),
    data.frame(
      scenario = source$scenario,
      metric = "High-priority\nJaccard",
      value = source$high_priority_jaccard,
      stringsAsFactors = FALSE
    )
  )
  plot_data$scenario <- factor(plot_data$scenario, levels = rev(scenario_order))
  plot_data$metric <- factor(
    plot_data$metric,
    levels = c("Rank rho", "Tier agreement", "High-priority\nJaccard")
  )
  plot_data$label <- scales::percent(plot_data$value, accuracy = 0.1)
  plot_data$label_colour <- ifelse(plot_data$value >= 0.88, "white", "#111820")
  heatmap_palette <- as.character(unlist(config$heatmap_palette))

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(x = metric, y = scenario, fill = value)
  ) +
    ggplot2::geom_tile(colour = "white", linewidth = 0.45) +
    ggplot2::geom_text(
      ggplot2::aes(label = label, colour = label_colour), size = 2.25
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_fill_gradientn(
      colours = heatmap_palette,
      limits = c(min(plot_data$value), 1),
      labels = scales::label_percent(accuracy = 1),
      name = "Similarity\nto baseline"
    ) +
    ggplot2::labs(
      x = NULL,
      y = NULL
    ) +
    priority_sensitivity_theme() +
    ggplot2::theme(
      axis.line = ggplot2::element_blank(),
      axis.ticks = ggplot2::element_blank(),
      axis.text.x = ggplot2::element_text(angle = 20, hjust = 1),
      legend.position = "right",
      panel.grid = ggplot2::element_blank()
    )
}
