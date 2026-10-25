prepare_score_decomposition <- function(compounds) {
  usable <- compounds[
    is.finite(compounds$Priority_score) &
      is.finite(compounds$Hazard_score) &
      is.finite(compounds$Exposure_score),
    ,
    drop = FALSE
  ]
  usable$score_bin <- floor(usable$Priority_score)
  wide <- dplyr::summarise(
    dplyr::group_by(usable, score_bin),
    compound_count = dplyr::n(),
    mean_priority_score = mean(Priority_score),
    mean_hazard = mean(Hazard_score),
    mean_exposure = mean(Exposure_score),
    .groups = "drop"
  )
  wide <- dplyr::arrange(wide, score_bin)
  if (any(abs(
    wide$mean_priority_score - wide$mean_hazard - wide$mean_exposure
  ) > 1e-8)) {
    stop("Mean hazard and exposure do not reconstruct mean priority.", call. = FALSE)
  }
  long <- rbind(
    data.frame(
      score_bin = wide$score_bin,
      compound_count = wide$compound_count,
      mean_priority_score = wide$mean_priority_score,
      score_component = "Hazard",
      mean_score_contribution = wide$mean_hazard
    ),
    data.frame(
      score_bin = wide$score_bin,
      compound_count = wide$compound_count,
      mean_priority_score = wide$mean_priority_score,
      score_component = "Exposure",
      mean_score_contribution = wide$mean_exposure
    )
  )
  list(
    source_data = list(
      score_decomposition = long,
      score_decomposition_wide = wide
    ),
    statistics = list(
      population_full = nrow(compounds),
      population_plotted = nrow(usable),
      score_bins = nrow(wide),
      decomposition_is_descriptive = TRUE
    )
  )
}
