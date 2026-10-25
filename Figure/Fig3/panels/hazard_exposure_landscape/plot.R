# This semantic panel inherits theme_classic(base_size = 8,
# base_family = "Arial") and delegates svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600) to the module build/export contract
# (assembled width_mm = 183; standalone dimensions are in figure.yml).

plot_hazard_exposure_landscape <- function(panel_data, config, variant = "publication") {
  pairs <- panel_data$hazard_exposure_pairs
  pairs$Priority_tier <- factor(pairs$Priority_tier, levels = priority_levels)
  pairs <- pairs[
    order(-pairs$compound_count, pairs$Hazard_score, pairs$Exposure_score),
    ,
    drop = FALSE
  ]
  priority_palette <- named_palette(config, "priority_palette")
  hazard_max <- as.numeric(config$thresholds$hazard_theoretical_max)
  exposure_max <- as.numeric(config$thresholds$exposure_theoretical_max)
  size_breaks <- c(25, 100, 250, 500, 1000)
  size_breaks <- size_breaks[size_breaks <= max(pairs$compound_count)]
  if (length(size_breaks) == 0L) size_breaks <- max(pairs$compound_count)

  boundary <- function(total, gate, tier) {
    left <- max(gate, total - exposure_max)
    if (gate == 0) {
      return(data.frame(Hazard_score = c(left, total),
                        Exposure_score = c(total - left, 0), tier = tier))
    }
    data.frame(Hazard_score = c(left, left, total - gate, hazard_max),
               Exposure_score = c(exposure_max, total - left, gate, gate), tier = tier)
  }
  boundaries <- rbind(
    boundary(config$thresholds$low_priority_upper,
             config$thresholds$moderate_component_min, "Moderate priority"),
    boundary(config$thresholds$high_priority_lower,
             config$thresholds$high_component_min, "High priority")
  )

  base_plot <- ggplot2::ggplot(
    pairs,
    ggplot2::aes(
      x = Hazard_score,
      y = Exposure_score,
      size = compound_count,
      fill = Priority_tier
    )
  ) +
    ggplot2::geom_path(
      data = boundaries,
      ggplot2::aes(x = Hazard_score, y = Exposure_score, group = tier),
      inherit.aes = FALSE, colour = "#677583",
      linetype = "22", linewidth = 0.55
    ) +
    ggplot2::geom_point(
      shape = 21,
      colour = "white",
      stroke = 0.16,
      alpha = 0.72
    ) +
    ggplot2::scale_fill_manual(
      values = priority_palette,
      breaks = c("Low priority", "Moderate priority", "High priority"),
      name = NULL,
      drop = FALSE
    ) +
    ggplot2::scale_size_area(
      max_size = 4.2,
      breaks = size_breaks,
      labels = scales::comma,
      name = "Compounds"
    ) +
    ggplot2::scale_x_continuous(
      breaks = seq(0, hazard_max, by = 2),
      labels = function(x) sprintf("%d", as.integer(x)),
      limits = c(0, hazard_max),
      expand = ggplot2::expansion(add = c(0.25, 0.25))
    ) +
    ggplot2::scale_y_continuous(
      breaks = seq(0, exposure_max, by = 2),
      labels = function(x) sprintf("%d", as.integer(x)),
      limits = c(0, exposure_max),
      expand = ggplot2::expansion(add = c(0.25, 0.25))
    ) +
    ggplot2::coord_fixed(ratio = 1, clip = "off") +
    ggplot2::labs(x = "Hazard score", y = "Exposure score") +
    priority_landscape_theme() +
    ggplot2::theme(
      legend.position = "bottom",
      legend.box = "vertical",
      legend.direction = "horizontal",
      legend.text = ggplot2::element_text(size = 7.0),
      legend.title = ggplot2::element_text(size = 7.0, colour = "#202830"),
      legend.key.height = grid::unit(5.2, "mm"),
      legend.spacing.y = grid::unit(1.0, "mm")
    ) +
    ggplot2::guides(
      fill = ggplot2::guide_legend(
        order = 1,
        nrow = 1,
        override.aes = list(
          size = 3.8,
          alpha = 0.82,
          fill = unname(priority_palette[c(
            "Low priority", "Moderate priority", "High priority"
          )])
        )
      ),
      size = ggplot2::guide_legend(
        order = 2,
        title.position = "left",
        nrow = 1,
        override.aes = list(
          shape = 21,
          fill = "#7B8794",
          colour = "white",
          alpha = 0.9
        )
      )
    )

  if (identical(variant, "publication")) {
    return(base_plot)
  }
  threshold <- as.numeric(config$display$hazard_exposure_label_min_count)
  labels <- pairs[pairs$compound_count >= threshold, , drop = FALSE]
  base_plot +
    ggplot2::geom_text(
      data = labels,
      ggplot2::aes(label = scales::comma(compound_count)),
      colour = "white",
      fontface = "bold",
      size = 1.95,
      show.legend = FALSE
    ) +
    ggplot2::geom_text(
      data = labels,
      ggplot2::aes(label = scales::comma(compound_count)),
      colour = "#202830",
      fontface = "bold",
      size = 1.45,
      show.legend = FALSE
    )
}
