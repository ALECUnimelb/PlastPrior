plot_policy_stable_review_context <- function(source_data, config) {
  plot_data <- source_data$stable_review_context_totals
  plot_data$regulatory_context <- factor(
    plot_data$regulatory_context,
    levels = policy_regulatory_context_levels
  )
  stable_count <- sum(plot_data$context_total)
  plot_data$proportion <- plot_data$context_total / stable_count
  plot_data$label <- paste0(
    scales::comma(plot_data$context_total), "  (",
    scales::percent(plot_data$proportion, accuracy = 1), ")"
  )
  context_palette <- c(
    "Monitoring/reporting or\nhazard classification" = "#39798B",
    "Inventory/registration/use only" = "#8AA9B2",
    "No linked GIC listing" = "#C97928"
  )
  maximum_count <- max(plot_data$context_total)
  label_offset <- maximum_count * 0.025
  axis_maximum <- maximum_count * 1.02
  plot_data$label_x <- ifelse(
    plot_data$proportion < 0.15,
    plot_data$context_total + label_offset * 0.55,
    plot_data$context_total - label_offset
  )
  plot_data$label_hjust <- ifelse(plot_data$proportion < 0.15, 0, 1)
  plot_data$label_colour <- ifelse(
    plot_data$proportion < 0.15, "#1C2633", "white"
  )
  axis_breaks <- pretty(c(0, max(plot_data$context_total)), n = 4)
  axis_breaks <- axis_breaks[
    axis_breaks >= 0 & axis_breaks <= max(plot_data$context_total)
  ]

  ggplot2::ggplot(
    plot_data,
    ggplot2::aes(
      x = context_total, y = regulatory_context,
      fill = regulatory_context
    )
  ) +
    ggplot2::geom_col(width = 0.58) +
    ggplot2::geom_text(
      ggplot2::aes(
        x = label_x, label = label,
        hjust = label_hjust, colour = label_colour
      ),
      size = 2.35, fontface = "bold"
    ) +
    ggplot2::scale_fill_manual(values = context_palette, guide = "none") +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_x_continuous(
      labels = scales::label_comma(), limits = c(0, axis_maximum),
      breaks = axis_breaks, expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::scale_y_discrete(
      labels = c(
        "Monitoring/reporting or\nhazard classification" =
          "Monitoring/reporting\nor hazard classification",
        "Inventory/registration/use only" =
          "Inventory/registration/use only",
        "No linked GIC listing" = "No linked GIC listing"
      )
    ) +
    ggplot2::labs(
      x = "Chemicals",
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
