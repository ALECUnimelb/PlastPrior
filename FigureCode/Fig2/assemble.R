tag_pbmt_plot <- function(plot, tag, config, reserve_title_space = FALSE) {
  tagged <- plot +
    ggplot2::labs(tag = tag) +
    ggplot2::theme(
      plot.tag = ggplot2::element_text(
        family = resolve_manuscript_font(),
        size = as.numeric(config$layout$tag_size_pt),
        face = "bold",
        colour = "#111820"
      ),
      plot.tag.position = c(0.006, 0.994)
    )
  if (isTRUE(reserve_title_space)) {
    tagged <- tagged + ggplot2::theme(
      plot.title = ggplot2::element_text(
        face = "bold", size = 7.1,
        margin = ggplot2::margin(l = 10, b = 2)
      ),
      plot.subtitle = ggplot2::element_text(
        size = 5.7, colour = "#555555",
        margin = ggplot2::margin(l = 10, b = 4)
      )
    )
  }
  tagged
}

center_pbmt_content <- function(plot, config, hjust = 0.5) {
  content_width <- as.numeric(config$layout$content_width_fraction)
  if (length(content_width) != 1L || !is.finite(content_width) ||
      content_width <= 0 || content_width > 1) {
    stop(
      "PBMT content_width_fraction must be a finite value in (0, 1].",
      call. = FALSE
    )
  }
  hjust <- as.numeric(hjust)
  if (length(hjust) != 1L || !is.finite(hjust) || hjust < 0 || hjust > 1) {
    stop(
      "PBMT content hjust must be a finite value in [0, 1].",
      call. = FALSE
    )
  }
  available_side_width <- 1 - content_width
  left_width <- available_side_width * hjust
  right_width <- available_side_width * (1 - hjust)
  patchwork::wrap_plots(
    patchwork::plot_spacer(),
    plot,
    patchwork::plot_spacer(),
    nrow = 1,
    widths = c(left_width, content_width, right_width)
  )
}

assemble_pbmt_concordance <- function(panel_plots, config) {
  required <- c("coverage")
  for (item in config$dimensions) {
    required <- c(
      required,
      paste0(item$dimension_id, "_agreement_severity"),
      paste0(item$dimension_id, "_score_matrix")
    )
  }
  missing <- setdiff(required, names(panel_plots))
  if (length(missing) > 0L) {
    stop(
      "Cannot assemble PBMT concordance; missing plot(s): ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }
  coverage <- tag_pbmt_plot(panel_plots$coverage, "a", config)
  dimensions <- list()
  for (item in config$dimensions) {
    severity_id <- paste0(item$dimension_id, "_agreement_severity")
    matrix_id <- paste0(item$dimension_id, "_score_matrix")
    tagged_severity <- tag_pbmt_plot(
      panel_plots[[severity_id]], item$panel_tag, config,
      reserve_title_space = TRUE
    )
    dimensions[[item$dimension_id]] <- assemble_pbmt_dimension(
      tagged_severity,
      panel_plots[[matrix_id]],
      config,
      show_y_axis = as.integer(item$order) %% 2L == 1L
    )
  }
  agreement_grid <-
    (dimensions$toxicity | dimensions$bioaccumulation) /
    (dimensions$mobility | dimensions$persistence) +
    patchwork::plot_layout(
      heights = as.numeric(unlist(config$layout$dimension_grid_heights))
    )
  centered_coverage <- center_pbmt_content(coverage, config)
  centered_agreement_grid <- center_pbmt_content(
    agreement_grid,
    config,
    hjust = config$layout$agreement_grid_hjust
  )
  centered_coverage / centered_agreement_grid +
    patchwork::plot_layout(
      heights = as.numeric(unlist(config$layout$main_heights))
    ) &
    ggplot2::theme(
      plot.background = ggplot2::element_rect(fill = "white", colour = NA)
    )
}
