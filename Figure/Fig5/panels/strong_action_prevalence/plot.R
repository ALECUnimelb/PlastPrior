plot_policy_strong_action_prevalence <- function(source_data, config) {
  plot_data <- source_data$strong_action_prevalence
  plot_data$priority_tier <- factor(
    plot_data$priority_tier, levels = policy_priority_levels
  )
  plot_data$label_x <- ifelse(
    plot_data$priority_tier == "High priority",
    plot_data$ci_low - 0.012,
    plot_data$ci_high + 0.012
  )
  plot_data$label_hjust <- ifelse(
    plot_data$priority_tier == "High priority", 1, 0
  )
  plot_data$label <- paste0(
    scales::comma(plot_data$strong_action_count), " / ",
    scales::comma(plot_data$compound_count), "  (",
    scales::percent(plot_data$proportion, accuracy = 0.1), ")"
  )
  high <- plot_data[plot_data$priority_tier == "High priority", ]
  palette <- policy_named_palette(config, "priority_palette")

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(x = proportion, y = priority_tier)
  ) +
    ggplot2::geom_segment(
      ggplot2::aes(x = ci_low, xend = ci_high, yend = priority_tier),
      linewidth = 0.6, colour = "#B4BDC7"
    ) +
    ggplot2::geom_point(
      ggplot2::aes(colour = priority_tier), size = 3.0
    ) +
    ggplot2::geom_text(
      ggplot2::aes(
        x = label_x, label = label, hjust = label_hjust
      ),
      size = 2.25, colour = "#1C2633"
    ) +
    ggplot2::scale_colour_manual(values = palette, guide = "none") +
    ggplot2::scale_x_continuous(
      labels = scales::label_percent(accuracy = 1),
      limits = c(0, as.numeric(config$thresholds$panel_a_x_maximum)),
      breaks = seq(
        0, as.numeric(config$thresholds$panel_a_x_maximum), by = 0.10
      ),
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::labs(
      title = "Strong-action prevalence rises with priority",
      subtitle = paste0(
        "High versus low priority: OR ",
        scales::number(high$odds_ratio, accuracy = 0.01),
        " (95% CI ", scales::number(high$or_ci_low, accuracy = 0.01),
        "\u2013", scales::number(high$or_ci_high, accuracy = 0.01), ")"
      ),
      x = "Chemicals in strong-action GIC categories",
      y = NULL
    ) +
    policy_theme() +
    ggplot2::theme(
      panel.grid.major.x = ggplot2::element_line(
        colour = "#E2E7EC", linewidth = 0.3
      )
    )
}
