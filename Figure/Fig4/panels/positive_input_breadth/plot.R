plot_priority_positive_input_breadth <- function(source_data, config) {
  plot_data <- source_data$positive_input_breadth
  metrics <- source_data$positive_input_breadth_metrics
  plot_data$priority_tier <- factor(
    plot_data$priority_tier, levels = priority_sensitivity_levels
  )
  plot_data$label <- ifelse(
    plot_data$compound_count > 0 & plot_data$within_tier_proportion >= 0.01,
    scales::percent(plot_data$within_tier_proportion, accuracy = 1),
    ""
  )
  plot_data$label_colour <- ifelse(
    plot_data$within_tier_proportion >= 0.12, "white", "#111820"
  )
  median_values <- stats::setNames(
    metrics$median_positive_inputs, metrics$priority_tier
  )

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(
      x = factor(positive_input_count), y = priority_tier,
      fill = within_tier_proportion
    )
  ) +
    ggplot2::geom_tile(colour = "white", linewidth = 0.35) +
    ggplot2::geom_text(
      ggplot2::aes(label = label, colour = label_colour), size = 2.05
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_fill_gradientn(
      colours = as.character(unlist(config$heatmap_palette)),
      limits = c(0, max(plot_data$within_tier_proportion)),
      labels = scales::label_percent(accuracy = 1),
      name = "Within-tier\nproportion"
    ) +
    ggplot2::labs(
      title = "Positive-scoring input breadth rises with priority",
      subtitle = paste0(
        "Median positive inputs: low ", median_values[["Low priority"]],
        ", moderate ", median_values[["Moderate priority"]],
        ", high ", median_values[["High priority"]]
      ),
      x = "Number of positive-scoring inputs (4 hazard + 6 exposure)",
      y = NULL
    ) +
    priority_sensitivity_theme() +
    ggplot2::theme(
      axis.line = ggplot2::element_blank(),
      axis.ticks = ggplot2::element_blank(),
      panel.grid = ggplot2::element_blank(),
      legend.position = "right"
    )
}
