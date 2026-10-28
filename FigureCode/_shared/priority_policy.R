# Classify unrounded domain sums; never use display bins or a total-score gate.
derive_priority_tier_shared <- function(
  scores, hazard, exposure, config, statuses = NULL,
  moderate_hazard_min = config$thresholds$moderate_hazard_min,
  high_hazard_gt = config$thresholds$high_hazard_gt,
  exposure_min = config$thresholds$exposure_min
) {
  if (length(scores) != length(hazard) || length(scores) != length(exposure) ||
      any(!is.finite(c(scores, hazard, exposure))) ||
      any(c(scores, hazard, exposure) < 0) ||
      any(abs(scores - hazard - exposure) > 1e-9)) {
    stop("Tier inputs must be finite, nonnegative and satisfy total = hazard + exposure.", call. = FALSE)
  }
  boundaries <- c(moderate_hazard_min, high_hazard_gt, exposure_min)
  if (length(boundaries) != 3L || any(!is.finite(boundaries)) ||
      moderate_hazard_min > high_hazard_gt) stop("Invalid H/E policy boundaries.")
  tier <- ifelse(hazard > high_hazard_gt & exposure >= exposure_min,
    "High priority",
    ifelse((hazard >= moderate_hazard_min & hazard <= high_hazard_gt & exposure >= exposure_min) |
           (hazard > high_hazard_gt & exposure < exposure_min), "Moderate priority", "Low priority"))
  if (!is.null(statuses)) {
    if (length(statuses) != length(scores) || anyNA(statuses)) stop("Priority data status must be present for every row.")
    tier[tolower(trimws(statuses)) == "no data"] <- "No data"
  }
  tier
}
