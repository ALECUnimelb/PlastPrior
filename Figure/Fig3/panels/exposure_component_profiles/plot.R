# This semantic panel inherits theme_classic(base_size = 8,
# base_family = "Arial") and delegates svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600) to the module build/export contract
# (assembled width_mm = 183; standalone dimensions are in figure.yml).

plot_exposure_component_profiles <- function(panel_data, config, variant = "publication") {
  profiles <- panel_data$exposure_component_profiles
  component_levels <- rev(names(exposure_dimensions))
  profiles$component <- factor(profiles$component, levels = component_levels)
  profiles$score_class <- factor(profiles$score_class, levels = exposure_profile_levels)
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
    profiles$score_class == "Score 0", "#202830", "white"
  )
  observed_levels <- exposure_profile_levels[
    exposure_profile_levels %in% profiles$score_class[profiles$compound_count > 0]
  ]
  palette <- named_palette(config, "exposure_profile_palette")
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
    ggplot2::coord_flip(clip = "off") +
    ggplot2::scale_fill_manual(
      values = palette,
      breaks = observed_levels,
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
      legend.text = ggplot2::element_text(size = 5.4),
      legend.key.width = grid::unit(2.4, "mm"),
      legend.key.height = grid::unit(2.4, "mm"),
      legend.spacing.x = grid::unit(0.8, "mm")
    ) +
    ggplot2::guides(fill = ggplot2::guide_legend(nrow = 2, byrow = TRUE))

  threshold <- if (identical(variant, "audit_all_values")) {
    as.numeric(config$display$audit_profile_label_min_fraction)
  } else {
    as.numeric(config$display$exposure_profile_label_min_fraction)
  }
  joint_high <- profiles[
    profiles$component == "Food-contact + biomonitoring" &
      profiles$score_class == "High (2)" &
      profiles$compound_count > 0,
    ,
    drop = FALSE
  ]
  labels <- profiles[
    profiles$proportion >= threshold &
      profiles$compound_count > 0 &
      !(profiles$component == "Food-contact + biomonitoring" &
          profiles$score_class == "High (2)"),
    ,
    drop = FALSE
  ]
  plot <- base_plot +
    ggplot2::geom_text(
      data = labels,
      ggplot2::aes(
        y = label_y,
        label = scales::comma(compound_count),
        colour = label_colour
      ),
      size = 1.9,
      fontface = "bold",
      check_overlap = TRUE,
      show.legend = FALSE
    ) +
    ggplot2::scale_colour_identity()
  if (nrow(joint_high) > 0L) {
    plot <- plot +
      ggplot2::geom_text(
        data = joint_high,
        ggplot2::aes(y = 1.01, label = scales::comma(compound_count)),
        inherit.aes = FALSE,
        x = 1,
        hjust = 0,
        size = 2,
        colour = "#202830"
      ) +
      ggplot2::theme(plot.margin = ggplot2::margin(5, 13, 5, 6))
  }
  plot
}
