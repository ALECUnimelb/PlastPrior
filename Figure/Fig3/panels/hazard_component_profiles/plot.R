# This semantic panel inherits theme_classic(base_size = 8,
# base_family = "Arial") and delegates svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600) to the module build/export contract
# (assembled width_mm = 183; standalone dimensions are in figure.yml).

plot_hazard_component_profiles <- function(panel_data, config, variant = "publication") {
  profiles <- panel_data$hazard_component_profiles
  profiles$component <- factor(
    profiles$component,
    levels = rev(names(hazard_components))
  )
  profiles$score_class <- factor(profiles$score_class, levels = hazard_profile_levels)
  profiles <- profiles[
    order(profiles$component_order, profiles$score_class_order),
    ,
    drop = FALSE
  ]
  profiles$label_y <- ave(
    profiles$proportion,
    profiles$component,
    FUN = function(value) cumsum(value) - value / 2
  )
  profiles$label_colour <- ifelse(
    profiles$score_class %in% c(
      "No usable evidence",
      "Evidence-supported zero (0)",
      "Score 0.25"
    ),
    "#202830",
    "white"
  )
  palette <- named_palette(config, "hazard_profile_palette")
  base_plot <- ggplot2::ggplot(
    profiles,
    ggplot2::aes(x = component, y = proportion, fill = score_class)
  ) +
    ggplot2::geom_col(
      width = 0.72,
      colour = "white",
      linewidth = 0.15,
      position = ggplot2::position_stack(reverse = TRUE)
    ) +
    ggplot2::coord_flip() +
    ggplot2::scale_fill_manual(
      values = palette,
      breaks = hazard_profile_levels,
      drop = FALSE
    ) +
    ggplot2::scale_y_continuous(
      labels = scales::percent_format(accuracy = 1),
      breaks = seq(0, 1, 0.25),
      expand = ggplot2::expansion(mult = c(0, 0.01))
    ) +
    ggplot2::labs(x = NULL, y = "Proportion of compounds") +
    priority_landscape_theme() +
    ggplot2::theme(
      axis.line.y = ggplot2::element_blank(),
      axis.ticks.y = ggplot2::element_blank(),
      legend.position = "bottom",
      legend.justification = "left",
      legend.text = ggplot2::element_text(size = 5.2),
      legend.key.width = grid::unit(2.2, "mm"),
      legend.key.height = grid::unit(2.2, "mm"),
      legend.spacing.x = grid::unit(0.7, "mm")
    ) +
    ggplot2::guides(fill = ggplot2::guide_legend(nrow = 2, byrow = TRUE))

  threshold <- if (identical(variant, "audit_all_values")) {
    as.numeric(config$display$audit_profile_label_min_fraction)
  } else {
    as.numeric(config$display$hazard_profile_label_min_fraction)
  }
  labels <- profiles[
    profiles$proportion >= threshold & profiles$compound_count > 0,
    ,
    drop = FALSE
  ]
  base_plot +
    ggplot2::geom_text(
      data = labels,
      ggplot2::aes(
        y = label_y,
        label = scales::comma(compound_count),
        colour = label_colour
      ),
      size = 2,
      fontface = "bold",
      check_overlap = TRUE,
      show.legend = FALSE
    ) +
    ggplot2::scale_colour_identity()
}
