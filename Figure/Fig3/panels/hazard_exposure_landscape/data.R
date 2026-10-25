prepare_hazard_exposure_landscape <- function(compounds, metadata, config) {
  usable <- compounds[
    is.finite(compounds$Hazard_score) & is.finite(compounds$Exposure_score),
    ,
    drop = FALSE
  ]
  pairs <- dplyr::count(
    usable,
    Hazard_score,
    Exposure_score,
    Priority_tier,
    name = "compound_count",
    .drop = TRUE
  )
  pairs <- dplyr::arrange(pairs, Hazard_score, Exposure_score)
  if (sum(pairs$compound_count) != nrow(usable)) {
    stop("Hazard/exposure score pairs do not conserve usable compounds.", call. = FALSE)
  }
  if (any(pairs$Hazard_score < 0) || any(pairs$Exposure_score < 0)) {
    stop("Hazard/exposure landscape contains negative scores.", call. = FALSE)
  }
  if (any(pairs$Hazard_score > as.numeric(config$thresholds$hazard_theoretical_max))) {
    stop("Hazard scores exceed the theoretical maximum.", call. = FALSE)
  }
  if (any(pairs$Exposure_score > as.numeric(config$thresholds$exposure_theoretical_max))) {
    stop("Exposure scores exceed the theoretical maximum.", call. = FALSE)
  }
  list(
    source_data = list(hazard_exposure_pairs = pairs),
    statistics = list(
      population_full = nrow(compounds),
      population_plotted = nrow(usable),
      occupied_score_pairs = nrow(pairs),
      pairs_count_ge_100 = sum(pairs$compound_count >= 100),
      pairs_count_ge_250 = sum(pairs$compound_count >= 250),
      hazard_score_max = metadata$hazard_score_max,
      exposure_score_max = metadata$exposure_score_max,
      hazard_axis_theoretical_max = as.numeric(config$thresholds$hazard_theoretical_max),
      exposure_axis_theoretical_max = as.numeric(config$thresholds$exposure_theoretical_max),
      raw_score_pairs_preserved = TRUE,
      scores_rounded = FALSE
    )
  )
}
