hazard_score_classes <- c(
  "No usable evidence",
  "Evidence-supported zero (0)",
  "Score 0.25",
  "Low (0.5)",
  "Moderate (1)",
  "High (2)"
)

classify_hazard_score <- function(values) {
  output <- rep("Unsupported score", length(values))
  output[is.na(values)] <- "No usable evidence"
  output[!is.na(values) & abs(values - 0) <= 1e-9] <- "Evidence-supported zero (0)"
  output[!is.na(values) & abs(values - 0.25) <= 1e-9] <- "Score 0.25"
  output[!is.na(values) & abs(values - 0.5) <= 1e-9] <- "Low (0.5)"
  output[!is.na(values) & abs(values - 1) <= 1e-9] <- "Moderate (1)"
  output[!is.na(values) & abs(values - 2) <= 1e-9] <- "High (2)"
  if (any(output == "Unsupported score")) {
    stop(
      "Unsupported hazard component score(s): ",
      paste(sort(unique(values[output == "Unsupported score"])), collapse = ", "),
      call. = FALSE
    )
  }
  output
}

prepare_hazard_component_profiles <- function(compounds) {
  rows <- list()
  row_index <- 1L
  for (component_order in seq_along(hazard_components)) {
    component <- names(hazard_components)[[component_order]]
    classes <- classify_hazard_score(compounds[[hazard_components[[component_order]]]])
    counts <- table(factor(classes, levels = hazard_score_classes))
    if (sum(counts) != nrow(compounds)) {
      stop(component, " profile does not conserve compounds.", call. = FALSE)
    }
    for (class_order in seq_along(hazard_score_classes)) {
      count <- as.integer(counts[[class_order]])
      rows[[row_index]] <- data.frame(
        component = component,
        component_order = component_order,
        score_class = hazard_score_classes[[class_order]],
        score_class_order = class_order,
        compound_count = count,
        proportion = count / nrow(compounds),
        stringsAsFactors = FALSE
      )
      row_index <- row_index + 1L
    }
  }
  profiles <- do.call(rbind, rows)
  list(
    source_data = list(hazard_component_profiles = profiles),
    statistics = list(
      population_full = nrow(compounds),
      components = names(hazard_components),
      missing_is_separate_from_zero = TRUE
    )
  )
}
