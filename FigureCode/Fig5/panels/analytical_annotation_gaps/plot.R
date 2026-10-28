plot_policy_analytical_annotation_gaps <- function(source_data, config) {
  plot_data <- source_data$analytical_annotation_gaps
  all_candidates <- plot_data[plot_data$scope == "All candidates", ]
  matched_platforms <- plot_data[plot_data$scope == "Matched subset", ]
  not_listed_count <- unique(all_candidates$denominator)
  no_match_count <- all_candidates$compound_count[
    all_candidates$display_category == "No SusDat match"
  ]
  matched_count <- all_candidates$compound_count[
    all_candidates$display_category == "SusDat matched"
  ]
  if (length(not_listed_count)==1L && (not_listed_count==0 || matched_count==0)) {
    labels <- c(paste0('No linked\nGIC listing\nn = ',not_listed_count),paste0('No SusDat match\nn = ',no_match_count),paste0('SusDat matched\nn = ',matched_count))
    return(ggplot()+annotate('segment',x=.28,xend=.50,y=.5,yend=c(.72,.28),colour='#8793A0')+
      geom_rect(data=data.frame(x=c(.15,.72,.72),y=c(.5,.72,.28),fill=c('#F0F3F6','#D7DDE4','#39798B')),aes(xmin=x-.14,xmax=x+.14,ymin=y-.12,ymax=y+.12,fill=fill))+
      annotate('text',x=c(.15,.72,.72),y=c(.5,.72,.28),label=labels,size=2.1,fontface='bold',colour=c('#1C2633','#1C2633','white'))+scale_fill_identity()+coord_cartesian(xlim=c(0,1),ylim=c(0,1),expand=FALSE)+theme_void(base_family='Arial'))
  }
  if (length(not_listed_count) != 1L || length(no_match_count) != 1L ||
      length(matched_count) != 1L || nrow(matched_platforms) < 1L) {
    stop("Analytical annotation flow inputs are invalid.", call. = FALSE)
  }
  matched_platforms <- matched_platforms[
    order(-matched_platforms$compound_count), , drop = FALSE
  ]

  analytical_palette <- policy_named_palette(config, "analytical_palette")
  platform_palette <- analytical_palette[
    as.character(matched_platforms$display_category)
  ]
  platform_palette[is.na(platform_palette)] <- "#AEB7C2"
  platform_count <- nrow(matched_platforms)
  platform_centres <- if (platform_count == 1L) {
    0.29
  } else {
    seq(0.49, 0.09, length.out = platform_count)
  }
  platform_spacing <- if (platform_count == 1L) 0.16 else {
    min(diff(sort(platform_centres)))
  }
  platform_height <- min(0.13, platform_spacing * 0.72)
  platform_boxes <- data.frame(
    xmin = 0.79,
    xmax = 0.995,
    ymin = platform_centres - platform_height / 2,
    ymax = platform_centres + platform_height / 2,
    y = platform_centres,
    fill = unname(platform_palette),
    label = paste0(
      vapply(
        as.character(matched_platforms$display_category),
        function(category) {
          switch(
            category,
            "Platform unresolved" = "Platform\nunresolved",
            "RPLC +ESI-HRMS" = "RPLC +ESI",
            "RPLC -ESI-HRMS" = "RPLC \u2212ESI",
            category
          )
        },
        character(1)
      ),
      "\n", scales::comma(matched_platforms$compound_count)
    ),
    stringsAsFactors = FALSE
  )
  major_boxes <- data.frame(
    xmin = c(0.01, 0.43, 0.43),
    xmax = c(0.29, 0.72, 0.72),
    ymin = c(0.39, 0.66, 0.20),
    ymax = c(0.63, 0.88, 0.42),
    fill = c("#F0F3F6", "#D7DDE4", "#39798B"),
    text_colour = c("#1C2633", "#1C2633", "white"),
    label = c(
      paste0("No linked\nGIC listing\nn = ", scales::comma(not_listed_count)),
      paste0(
        "No SusDat match\n", scales::comma(no_match_count), "  (",
        scales::percent(no_match_count / not_listed_count, accuracy = 1), ")"
      ),
      paste0(
        "SusDat matched\n", scales::comma(matched_count), "  (",
        scales::percent(matched_count / not_listed_count, accuracy = 1), ")"
      )
    ),
    stringsAsFactors = FALSE
  )
  first_stage_segments <- data.frame(
    x = c(0.29, 0.36, 0.36),
    xend = c(0.36, 0.36, 0.43),
    y = c(0.51, 0.31, 0.31),
    yend = c(0.51, 0.77, 0.31)
  )
  first_stage_segments <- rbind(
    first_stage_segments,
    data.frame(x = 0.36, xend = 0.43, y = 0.77, yend = 0.77)
  )
  second_stage_segments <- data.frame(
    x = c(0.72, 0.76),
    xend = c(0.76, 0.76),
    y = c(0.31, min(platform_centres)),
    yend = c(0.31, max(platform_centres))
  )
  branch_segments <- data.frame(
    x = 0.76, xend = 0.79,
    y = platform_centres, yend = platform_centres
  )

  ggplot2::ggplot() +
    ggplot2::geom_segment(
      data = first_stage_segments,
      ggplot2::aes(x = x, xend = xend, y = y, yend = yend),
      linewidth = 0.45, colour = "#8793A0"
    ) +
    ggplot2::geom_segment(
      data = second_stage_segments,
      ggplot2::aes(x = x, xend = xend, y = y, yend = yend),
      linewidth = 0.45, colour = "#8793A0"
    ) +
    ggplot2::geom_segment(
      data = branch_segments,
      ggplot2::aes(x = x, xend = xend, y = y, yend = yend),
      linewidth = 0.45, colour = "#8793A0"
    ) +
    ggplot2::geom_rect(
      data = major_boxes,
      ggplot2::aes(
        xmin = xmin, xmax = xmax, ymin = ymin, ymax = ymax,
        fill = fill
      ),
      colour = "white", linewidth = 0.5
    ) +
    ggplot2::geom_text(
      data = major_boxes,
      ggplot2::aes(
        x = (xmin + xmax) / 2, y = (ymin + ymax) / 2,
        label = label, colour = text_colour
      ),
      size = 2.1, fontface = "bold", lineheight = 0.95
    ) +
    ggplot2::geom_rect(
      data = platform_boxes,
      ggplot2::aes(
        xmin = xmin, xmax = xmax, ymin = ymin, ymax = ymax,
        fill = fill
      ),
      colour = "white", linewidth = 0.5
    ) +
    ggplot2::geom_text(
      data = platform_boxes,
      ggplot2::aes(
        x = (xmin + xmax) / 2, y = y, label = label
      ),
      size = 1.75, fontface = "bold", colour = "white", lineheight = 0.9
    ) +
    ggplot2::annotate(
      "text", x = 0.88, y = 0.59,
      label = paste0("Among ", scales::comma(matched_count), if (matched_count == 1) " match" else " matches"),
      size = 1.85, fontface = "bold", colour = "#65717E"
    ) +
    ggplot2::scale_fill_identity() +
    ggplot2::scale_colour_identity() +
    ggplot2::coord_cartesian(
      xlim = c(0, 1), ylim = c(0, 1), expand = FALSE, clip = "off"
    ) +
    ggplot2::labs(
      x = NULL,
      y = NULL
    ) +
    policy_theme() +
    ggplot2::theme(
      axis.line = ggplot2::element_blank(),
      axis.ticks = ggplot2::element_blank(),
      axis.text = ggplot2::element_blank(),
      panel.grid = ggplot2::element_blank(),
      plot.margin = ggplot2::margin(6, 6, 6, 8)
    )
}
