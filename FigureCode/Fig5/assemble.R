assemble_policy_concordance_and_review_gaps <- function(panel_plots, config) {
  required <- c(
    "strong_action_prevalence", "ranking_capture",
    "stable_review_context", "analytical_annotation_gaps"
  )
  missing <- setdiff(required, names(panel_plots))
  if (length(missing) > 0L) {
    stop(
      "Cannot assemble policy concordance figure; missing plot(s): ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }
  widths <- as.numeric(unlist(config$layout$widths))
  heights <- as.numeric(unlist(config$layout$heights))
  figure <-
    (panel_plots$strong_action_prevalence | panel_plots$ranking_capture) /
    (panel_plots$stable_review_context | panel_plots$analytical_annotation_gaps) +
    patchwork::plot_layout(widths = widths, heights = heights) +
    patchwork::plot_annotation(tag_levels = "a")
  figure &
    ggplot2::theme(
      plot.tag = ggplot2::element_text(
        family = resolve_manuscript_font(),
        size = as.numeric(config$layout$tag_size_pt),
        face = "bold", colour = "#111820"
      ),
      plot.background = ggplot2::element_rect(fill = "white", colour = NA)
    )
}
