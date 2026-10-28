prepare_priority_score_distribution <- function(compounds, metadata) {
  usable <- compounds[is.finite(compounds$Priority_score), , drop = FALSE]
  usable$score_bin <- floor(usable$Priority_score)
  distribution <- dplyr::count(
    usable,
    score_bin,
    Priority_tier,
    name = "compound_count",
    .drop = TRUE
  )
  distribution <- dplyr::arrange(distribution, score_bin)
  tier_counts <- table(factor(compounds$Priority_tier, levels = priority_levels))
  tiers <- data.frame(
    priority_tier = priority_levels,
    compound_count = as.integer(tier_counts),
    stringsAsFactors = FALSE
  )
  if (sum(distribution$compound_count) != nrow(usable)) {
    stop("Priority-score distribution does not conserve usable compounds.", call. = FALSE)
  }
  list(
    source_data = list(
      priority_distribution = distribution,
      priority_tiers = tiers
    ),
    statistics = list(
      population_full = nrow(compounds),
      population_plotted = nrow(usable),
      score_bins = length(unique(distribution$score_bin)),
      priority_score_min = metadata$priority_score_min,
      priority_score_max = metadata$priority_score_max,
      priority_score_median = metadata$priority_score_median,
      priority_tier_counts = metadata$priority_tier_counts
    )
  )
}
