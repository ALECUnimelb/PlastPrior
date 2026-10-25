# Versioned figure-side policy; keeps the Figures bundle independent of Python.
priority_config_for_snapshot <- function(snapshot, config) {
  version <- snapshot$manifest$scientific_metadata$priority_tier_policy_version
  if (is.null(version)) version <- "legacy-additive-tiers"
  if (!version %in% c("legacy-additive-tiers", "priority-dual-gates-v1")) {
    stop("Unsupported snapshot priority tier policy: ", version, call. = FALSE)
  }
  config$priority_tier_policy_version <- version
  config$thresholds$moderate_component_min <- if (version == "priority-dual-gates-v1") 2 else 0
  config$thresholds$high_component_min <- if (version == "priority-dual-gates-v1") 4 else 0
  config
}

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
    stop("Resolve the snapshot priority policy before deriving tiers.", call. = FALSE)
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
