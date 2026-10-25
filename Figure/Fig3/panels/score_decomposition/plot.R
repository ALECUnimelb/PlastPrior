# This semantic panel inherits theme_classic(base_size = 8,
# base_family = "Arial") and delegates svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600) to the module build/export contract
# (assembled width_mm = 183; standalone dimensions are in figure.yml).

plot_score_decomposition <- function(panel_data, config, variant = "publication") {
  decomposition <- panel_data$score_decomposition
  decomposition$score_component <- factor(
    decomposition$score_component,
    levels = c("Hazard", "Exposure")
  )
  exposure_lookup <- decomposition[
    decomposition$score_component == "Exposure",
    c("score_bin", "mean_score_contribution")
  ]
  names(exposure_lookup)[[2]] <- "exposure_base"
  decomposition <- merge(decomposition, exposure_lookup, by = "score_bin", all.x = TRUE)
  decomposition$label_y <- ifelse(
    decomposition$score_component == "Exposure",
    decomposition$mean_score_contribution / 2,
    decomposition$exposure_base + decomposition$mean_score_contribution / 2
  )
  score_palette <- named_palette(config, "score_component_palette")
  base_plot <- ggplot2::ggplot(
    decomposition,
    ggplot2::aes(
      x = score_bin,
      y = mean_score_contribution,
      fill = score_component
    )
  ) +
    ggplot2::geom_col(width = 0.80, colour = "white", linewidth = 0.12) +
    ggplot2::scale_fill_manual(values = score_palette, breaks = c("Hazard", "Exposure")) +
    ggplot2::scale_x_continuous(
      breaks = seq(min(decomposition$score_bin), max(decomposition$score_bin), by = 2),
      expand = ggplot2::expansion(add = c(0.5, 0.5))
    ) +
    ggplot2::scale_y_continuous(expand = ggplot2::expansion(mult = c(0, 0.06))) +
    ggplot2::labs(
      x = "Priority score (1-point intervals)",
      y = "Mean score contribution"
    ) +
    priority_landscape_theme() +
    ggplot2::theme(legend.position = "top", legend.justification = "left")

  threshold <- as.numeric(config$display$score_decomposition_label_min_contribution)
  if (identical(variant, "audit_all_values")) threshold <- 0
  labels <- decomposition[decomposition$mean_score_contribution >= threshold, , drop = FALSE]
  round_half_up <- function(values) floor(values + 0.5)
  base_plot + ggplot2::geom_text(
    data = labels,
    ggplot2::aes(
      y = label_y,
      label = sprintf("%d", round_half_up(mean_score_contribution))
    ),
    colour = "white",
    fontface = "bold",
    size = 1.75,
    check_overlap = TRUE
  )
}
