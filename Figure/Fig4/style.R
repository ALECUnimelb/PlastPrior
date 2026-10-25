priority_sensitivity_levels <- c(
  "Low priority", "Moderate priority", "High priority"
)

priority_sensitivity_named_palette <- function(config, field) {
  values <- unlist(config[[field]], use.names = TRUE)
  stats::setNames(as.character(values), names(values))
}

priority_sensitivity_panel_config <- function(config, panel_id) {
  matches <- Filter(
    function(item) identical(item$panel_id, panel_id),
    config$panels
  )
  if (length(matches) != 1L) {
    stop("Unknown priority sensitivity panel ID: ", panel_id, call. = FALSE)
  }
  matches[[1]]
}

priority_sensitivity_theme <- function(base_size = 7.4) {
  theme_manuscript(base_size = base_size) +
    ggplot2::theme(
      legend.title = ggplot2::element_blank(),
      legend.key.height = grid::unit(3.2, "mm"),
      legend.key.width = grid::unit(4.2, "mm"),
      legend.margin = ggplot2::margin(0, 0, 0, 0),
      plot.title = ggplot2::element_text(
        face = "bold", size = base_size + 0.9, hjust = 0,
        margin = ggplot2::margin(b = 1.5)
      ),
      plot.subtitle = ggplot2::element_text(
        colour = "#5B6673", size = base_size - 0.3, hjust = 0,
        margin = ggplot2::margin(b = 3.5)
      ),
      plot.margin = ggplot2::margin(5, 6, 5, 7)
    )
}
