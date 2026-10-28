prepare_regulatory_context_inset <- function(compounds) {
  observed <- dplyr::count(
    compounds,
    Priority_tier,
    GIC_regulatory_status_display,
    name = "compound_count",
    .drop = TRUE
  )
  names(observed)[names(observed) == "Priority_tier"] <- "priority_tier"
  names(observed)[names(observed) == "GIC_regulatory_status_display"] <- "regulatory_status"
  complete <- expand.grid(
    priority_tier = priority_levels,
    regulatory_status = regulatory_levels,
    stringsAsFactors = FALSE
  )
  cross <- merge(
    complete,
    observed,
    by = c("priority_tier", "regulatory_status"),
    all.x = TRUE,
    sort = FALSE
  )
  cross$compound_count[is.na(cross$compound_count)] <- 0L
  cross$priority_order <- match(cross$priority_tier, priority_levels)
  cross$regulatory_order <- match(cross$regulatory_status, regulatory_levels)
  cross <- cross[order(cross$priority_order, cross$regulatory_order), , drop = FALSE]

  tier_totals <- stats::aggregate(
    compound_count ~ priority_tier + priority_order,
    cross,
    sum
  )
  tier_totals <- tier_totals[order(tier_totals$priority_order), , drop = FALSE]
  regulatory_totals <- stats::aggregate(
    compound_count ~ regulatory_status + regulatory_order,
    cross,
    sum
  )
  regulatory_totals <- regulatory_totals[
    order(regulatory_totals$regulatory_order), , drop = FALSE
  ]
  if (sum(cross$compound_count) != nrow(compounds)) {
    stop("GIC inset cross-tabulation does not conserve compounds.", call. = FALSE)
  }
  list(
    source_data = list(
      priority_regulatory_cross = cross,
      priority_tier_totals = tier_totals,
      regulatory_status_totals = regulatory_totals
    ),
    statistics = list(
      population_full = nrow(compounds),
      regulatory_context_is_score_input = FALSE,
      matched_gic_listing = sum(
        compounds$GIC_regulatory_status_display != "No matched GIC listing"
      )
    )
  )
}
