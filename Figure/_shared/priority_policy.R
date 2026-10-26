# Current complete-evidence cohort only; missing score inputs are rejected.
derive_priority_tier_shared <- function(
  scores, hazard, exposure, config, statuses = NULL,
  low_threshold = config$thresholds$low_priority_upper,
  high_threshold = config$thresholds$high_priority_lower
) {
  if (length(scores) != length(hazard) || length(scores) != length(exposure) ||
      any(!is.finite(c(scores, hazard, exposure))) ||
      any(c(scores, hazard, exposure) < 0) ||
      any(abs(scores - hazard - exposure) > 1e-9)) {
    stop("Tier inputs must be finite, nonnegative and satisfy total = hazard + exposure.", call. = FALSE)
  }
  moderate_min <- as.numeric(config$thresholds$moderate_component_min)
  high_min <- as.numeric(config$thresholds$high_component_min)
  if (length(moderate_min) != 1L || length(high_min) != 1L) {
    stop("Resolve the locked current priority policy before deriving tiers.", call. = FALSE)
  }
  tier <- ifelse(
    scores >= high_threshold & hazard >= high_min & exposure >= high_min,
    "High priority",
    ifelse(scores >= low_threshold & hazard >= moderate_min & exposure >= moderate_min,
           "Moderate priority", "Low priority")
  )
  if (!is.null(statuses)) {
    if (length(statuses) != length(scores) || anyNA(statuses)) {
      stop("Priority data status must be present for every row.", call. = FALSE)
    }
    tier[tolower(trimws(statuses)) == "no data"] <- "No data"
  }
  tier
}
