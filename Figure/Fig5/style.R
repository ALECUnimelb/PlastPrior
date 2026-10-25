policy_priority_levels <- c(
  "Low priority", "Moderate priority", "High priority"
)

policy_method_levels <- c(
  "Integrated score", "Integrated, inventory removed",
  "Exposure only", "Hazard only"
)

policy_pathway_levels <- c(
  "Hazard-led", "Joint hazard-exposure", "Exposure-led", "Other"
)

policy_regulatory_context_levels <- c(
  "No linked GIC listing",
  "Inventory/registration/use only",
  "Monitoring/reporting or\nhazard classification"
)

policy_analytical_levels <- c(
  "No NORMAN match", "NORMAN match; platform unresolved",
  "GC-EI-MS", "RPLC +ESI-HRMS", "RPLC -ESI-HRMS",
  "Missing annotation"
)

policy_named_palette <- function(config, field) {
  values <- unlist(config[[field]], use.names = TRUE)
  stats::setNames(as.character(values), names(values))
}

policy_panel_config <- function(config, panel_id) {
  matches <- Filter(
    function(item) identical(item$panel_id, panel_id),
    config$panels
  )
  if (length(matches) != 1L) {
    stop("Unknown policy concordance panel ID: ", panel_id, call. = FALSE)
  }
  matches[[1]]
}

policy_theme <- function(base_size = 7.2) {
  theme_manuscript(base_size = base_size) +
    ggplot2::theme(
      legend.title = ggplot2::element_blank(),
      legend.key.size = grid::unit(3.1, "mm"),
      legend.margin = ggplot2::margin(0, 0, 0, 0),
      plot.title = ggplot2::element_text(
        face = "bold", size = base_size + 0.6, hjust = 0,
        margin = ggplot2::margin(b = 1.5)
      ),
      plot.subtitle = ggplot2::element_text(
        colour = "#65717E", size = base_size - 0.2, hjust = 0,
        margin = ggplot2::margin(b = 3.5)
      ),
      plot.margin = ggplot2::margin(6, 7, 6, 8)
    )
}
