tag_priority_sensitivity_panel <- function(plot, tag, config, tag_x = 0.006) {
  plot +
    ggplot2::labs(tag = tag) +
    ggplot2::theme(
      plot.tag = ggplot2::element_text(
        family = resolve_manuscript_font(),
        size = as.numeric(config$layout$tag_size_pt),
        face = "bold",
        colour = "#111820"
      ),
      plot.tag.position = c(tag_x, 0.994),
      plot.title = ggplot2::element_text(margin = ggplot2::margin(l = 9, b = 1.5)),
      plot.subtitle = ggplot2::element_text(
        margin = ggplot2::margin(l = 9, b = 3.5)
      )
    )
}

assemble_priority_sensitivity_and_robustness <- function(panel_plots, config) {
  required <- c("leave_one_input_out", "scenario_sensitivity")
  missing <- setdiff(required, names(panel_plots))
  if (length(missing) > 0L) {
    stop(
      "Cannot assemble priority sensitivity figure; missing plot(s): ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }
  tagged <- list(
    leave_one_input_out = tag_priority_sensitivity_panel(
      panel_plots$leave_one_input_out, "a", config
    ),
    scenario_sensitivity = tag_priority_sensitivity_panel(
      panel_plots$scenario_sensitivity, "b", config, tag_x = 0.275
    )
  )
  patchwork::wrap_plots(
    tagged,
    nrow = 1,
    widths = as.numeric(unlist(config$layout$main_widths))
  ) &
    ggplot2::theme(
      plot.background = ggplot2::element_rect(fill = "white", colour = NA)
    )
}

assemble_priority_positive_input_context <- function(panel_plots, config) {
  required <- as.character(unlist(
    config$supplementary$panel_ids, use.names = FALSE
  ))
  missing <- setdiff(required, names(panel_plots))
  if (length(missing) > 0L) {
    stop(
      "Cannot assemble positive-input context; missing plot(s): ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }
  tagged <- list(
    positive_input_breadth = tag_priority_sensitivity_panel(
      panel_plots$positive_input_breadth, "a", config
    ),
    positive_input_prevalence = tag_priority_sensitivity_panel(
      panel_plots$positive_input_prevalence, "b", config, tag_x = 0.18
    )
  )
  patchwork::wrap_plots(
    tagged,
    nrow = 1,
    widths = as.numeric(unlist(config$layout$supplementary_widths))
  ) &
    ggplot2::theme(
      plot.background = ggplot2::element_rect(fill = "white", colour = NA)
    )
}
