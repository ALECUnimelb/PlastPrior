# This semantic inset inherits theme_classic(base_size = 8,
# base_family = "Arial") and delegates svglite::svglite(),
# grDevices::cairo_pdf(), ragg::agg_png(res = 600), and
# ragg::agg_tiff(res = 600) to the module build/export contract
# (assembled width_mm = 183; standalone dimensions are in figure.yml).

relative_luminance_priority <- function(hex_colour) {
  rgb <- grDevices::col2rgb(hex_colour) / 255
  linear <- ifelse(
    rgb <= 0.04045,
    rgb / 12.92,
    ((rgb + 0.055) / 1.055)^2.4
  )
  sum(c(0.2126, 0.7152, 0.0722) * linear)
}

contrast_text_priority <- function(categories, palette) {
  vapply(
    as.character(categories),
    function(category) {
      if (relative_luminance_priority(palette[[category]]) < 0.43) {
        "white"
      } else {
        "#202830"
      }
    },
    character(1)
  )
}

spread_regulatory_callout_angles <- function(
  angles,
  total,
  min_separation_degrees
) {
  angles <- as.numeric(angles)
  total <- as.numeric(total)
  min_separation_degrees <- as.numeric(min_separation_degrees)
  if (length(angles) <= 1L) {
    return(angles)
  }
  if (length(total) != 1L || !is.finite(total) || total <= 0 ||
      length(min_separation_degrees) != 1L ||
      !is.finite(min_separation_degrees) ||
      min_separation_degrees <= 0 || min_separation_degrees >= 360) {
    stop("Invalid regulatory callout packing parameters.", call. = FALSE)
  }
  min_gap <- total * min_separation_degrees / 360
  if (min_gap * (length(angles) - 1L) > total) {
    stop("Regulatory callout labels cannot fit around the circle.", call. = FALSE)
  }

  angle_order <- order(angles)
  ordered_angles <- angles[angle_order]
  packed <- ordered_angles
  for (index in 2:length(packed)) {
    packed[[index]] <- max(
      ordered_angles[[index]],
      packed[[index - 1L]] + min_gap
    )
  }
  packed <- packed + mean(ordered_angles) - mean(packed)
  if (min(packed) < 0) {
    packed <- packed - min(packed)
  }
  if (max(packed) > total) {
    packed <- packed - (max(packed) - total)
  }
  if (min(packed) < 0 || any(diff(packed) < min_gap - 1e-9)) {
    stop("Regulatory callout packing exceeded the circular bounds.", call. = FALSE)
  }

  restored <- numeric(length(angles))
  restored[angle_order] <- packed
  restored
}

plot_regulatory_context_inset <- function(panel_data, config, variant = "publication") {
  cross <- panel_data$priority_regulatory_cross
  tier_totals <- panel_data$priority_tier_totals
  cross <- cross[order(cross$priority_order, cross$regulatory_order), , drop = FALSE]
  tier_totals <- tier_totals[order(tier_totals$priority_order), , drop = FALSE]
  total <- sum(cross$compound_count)

  cross$ymax <- cumsum(cross$compound_count)
  cross$ymin <- c(0, utils::head(cross$ymax, -1))
  cross$ymid <- (cross$ymin + cross$ymax) / 2
  tier_totals$ymax <- cumsum(tier_totals$compound_count)
  tier_totals$ymin <- c(0, utils::head(tier_totals$ymax, -1))
  tier_totals$ymid <- (tier_totals$ymin + tier_totals$ymax) / 2
  cross$regulatory_status <- factor(cross$regulatory_status, levels = regulatory_levels)
  tier_totals$priority_tier <- factor(tier_totals$priority_tier, levels = priority_levels)

  priority_palette <- named_palette(config, "priority_palette")
  regulatory_palette <- named_palette(config, "regulatory_palette")
  cross$label_colour <- contrast_text_priority(
    cross$regulatory_status, regulatory_palette
  )
  tier_totals$label_colour <- contrast_text_priority(
    tier_totals$priority_tier, priority_palette
  )
  base_family <- resolve_manuscript_font()

  plot <- ggplot2::ggplot() +
    ggplot2::geom_rect(
      data = cross,
      ggplot2::aes(
        xmin = 2.05, xmax = 2.95, ymin = ymin, ymax = ymax,
        fill = regulatory_status
      ),
      colour = "white",
      linewidth = 0.18
    ) +
    ggplot2::geom_rect(
      data = tier_totals,
      ggplot2::aes(
        xmin = 0.55, xmax = 1.95, ymin = ymin, ymax = ymax,
        fill = priority_tier
      ),
      colour = "white",
      linewidth = 0.22
    ) +
    ggplot2::geom_text(
      data = tier_totals[tier_totals$compound_count / total >= 0.05, , drop = FALSE],
      ggplot2::aes(
        x = 1.25, y = ymid,
        label = scales::comma(compound_count),
        colour = label_colour
      ),
      fontface = "bold",
      size = 2.35,
      show.legend = FALSE
    ) +
    ggplot2::coord_polar(theta = "y", clip = "off") +
    ggplot2::xlim(0, 3.72) +
    ggplot2::scale_fill_manual(
      values = c(priority_palette, regulatory_palette),
      breaks = regulatory_levels,
      labels = c("Prohibited/phase-out", "Restricted/authorisation",
                 "Candidate/high concern", "Monitoring/reporting/\nhazard",
                 "Inventory/registration/\nuse", "No matched GIC listing"),
      drop = FALSE
    ) +
    ggplot2::scale_colour_identity() +
    ggplot2::labs(fill = NULL) +
    ggplot2::theme_void(base_family = base_family) +
    ggplot2::theme(
      legend.position = "right",
      legend.title = ggplot2::element_blank(),
      legend.text = ggplot2::element_text(size = 5.4),
      legend.key.size = grid::unit(2.8, "mm"),
      legend.box = "vertical",
      plot.margin = ggplot2::margin(2, 1, 2, 1)
    ) +
    ggplot2::guides(fill = ggplot2::guide_legend(ncol = 1, byrow = TRUE))

  small_tiers <- tier_totals[tier_totals$compound_count > 0 & tier_totals$compound_count / total < 0.05, , drop=FALSE]
  if (nrow(small_tiers)>0) plot <- plot +
    ggplot2::geom_segment(data=small_tiers,ggplot2::aes(x=1.95,xend=3.12,y=ymid,yend=ymid),colour='#202830',linewidth=.25) +
    ggplot2::geom_text(data=small_tiers,ggplot2::aes(x=3.45,y=ymid,label=scales::comma(compound_count)),colour='#202830',size=2.1,fontface='bold')

  fraction_threshold <- if (identical(variant, "audit_all_values")) {
    0
  } else {
    as.numeric(config$display$regulatory_internal_label_min_fraction)
  }
  cross$fraction <- cross$compound_count / total
  internal_labels <- cross[
    cross$compound_count > 0 & cross$fraction >= fraction_threshold,
    ,
    drop = FALSE
  ]
  callout_labels <- cross[
    cross$compound_count > 0 & cross$fraction < fraction_threshold,
    ,
    drop = FALSE
  ]
  plot <- plot + ggplot2::geom_text(
    data = internal_labels,
    ggplot2::aes(
      x = 2.50, y = ymid,
      label = scales::comma(compound_count),
      colour = label_colour
    ),
    size = 1.65,
    fontface = "bold",
    show.legend = FALSE
  )
  if (nrow(callout_labels) > 0L &&
      (identical(variant, "audit_all_values") || isTRUE(config$display$regulatory_show_small_callouts))) {
    callout_labels$label_y <- spread_regulatory_callout_angles(
      callout_labels$ymid,
      total,
      as.numeric(config$display$regulatory_callout_min_separation_degrees)
    )
    callout_labels$label_x <- 3.24 +
      0.32 * ((seq_len(nrow(callout_labels)) - 1L) %% 2L)
    plot <- plot +
      ggplot2::geom_segment(
        data = callout_labels,
        ggplot2::aes(
          x = 2.93, xend = label_x - 0.05,
          y = ymid, yend = label_y
        ),
        colour = "#616A73",
        linewidth = 0.28,
        show.legend = FALSE
      ) +
      ggplot2::geom_text(
        data = callout_labels,
        ggplot2::aes(
          x = label_x, y = label_y,
          label = scales::comma(compound_count)
        ),
        colour = "#202830",
        fontface = "bold",
        size = 1.62,
        show.legend = FALSE
      )
  }
  plot
}
