priority_levels <- c(
  "No data", "Low priority", "Moderate priority", "High priority"
)

regulatory_levels <- c(
  "Prohibited/phase-out",
  "Restricted/authorisation",
  "Candidate/high concern",
  "Monitoring/reporting/hazard",
  "Inventory/registration/use",
  "No matched GIC listing"
)

hazard_profile_levels <- c(
  "No usable evidence",
  "Evidence-supported zero (0)",
  "Low confidence (0.25)",
  "Low (0.5)",
  "Moderate (1)",
  "High (2)"
)

exposure_profile_levels <- c(
  "Score 0", "Low (0.5)", "Moderate (1)", "High (2)"
)

named_palette <- function(config, key) {
  values <- unlist(config[[key]], use.names = TRUE)
  stats::setNames(as.character(values), names(values))
}

priority_landscape_theme <- function(
  base_size = 8,
  base_family = resolve_manuscript_font()
) {
  ggplot2::theme_classic(base_size = base_size, base_family = base_family) +
    ggplot2::theme(
      axis.line = ggplot2::element_line(linewidth = 0.35, colour = "#222222"),
      axis.ticks = ggplot2::element_line(linewidth = 0.35, colour = "#222222"),
      axis.text = ggplot2::element_text(colour = "#30343A"),
      axis.title = ggplot2::element_text(colour = "#202830"),
      legend.title = ggplot2::element_blank(),
      legend.text = ggplot2::element_text(size = base_size - 1),
      legend.key.height = grid::unit(3, "mm"),
      panel.grid = ggplot2::element_blank(),
      plot.background = ggplot2::element_rect(fill = "white", colour = NA),
      panel.background = ggplot2::element_rect(fill = "white", colour = NA),
      plot.margin = ggplot2::margin(5, 6, 5, 6)
    )
}

panel_config <- function(config, panel_id) {
  ids <- vapply(config$panels, function(panel) panel$panel_id, character(1))
  if (!(panel_id %in% ids)) {
    stop("Unknown panel ID in figure.yml: ", panel_id, call. = FALSE)
  }
  config$panels[[match(panel_id, ids)]]
}
