policy_component_specs <- function(config) {
  data.frame(
    component = vapply(config$components, function(item) item$component, character(1)),
    family = vapply(config$components, function(item) item$family, character(1)),
    score_column = vapply(
      config$components, function(item) item$score_column, character(1)
    ),
    multiplier = vapply(
      config$components, function(item) as.numeric(item$multiplier), numeric(1)
    ),
    theoretical_maximum = vapply(
      config$components,
      function(item) as.numeric(item$theoretical_maximum),
      numeric(1)
    ),
    stringsAsFactors = FALSE
  )
}

policy_required_fields <- function(config) {
  specs <- policy_component_specs(config)
  unique(c(
    "Inchikey_std", "Name_std", "CAS", "Priority_tier",
    "GIC_regulatory_status", "Analytical_detectability",
    "resolution_route", "source_dbs",
    "Exposure_inventory_listing_count", "Hazard_score", "Exposure_score",
    "Priority_score", specs$score_column
  ))
}

policy_numeric <- function(values, column_name, missing_as_zero = FALSE) {
  text <- trimws(ifelse(is.na(values), "", as.character(values)))
  output <- suppressWarnings(as.numeric(text))
  invalid <- nzchar(text) & (!is.finite(output) | is.na(output))
  if (any(invalid)) {
    stop(column_name, " contains invalid numeric values.", call. = FALSE)
  }
  if (!missing_as_zero && any(!nzchar(text))) {
    stop(column_name, " contains missing values.", call. = FALSE)
  }
  if (missing_as_zero) stop("Missing-value imputation is prohibited.")
  output
}

policy_assert_equal <- function(observed, expected, message, tolerance = 1e-9) {
  mismatch <- !is.finite(observed) | !is.finite(expected) |
    abs(observed - expected) > tolerance
  if (any(mismatch)) {
    stop(message, " for ", sum(mismatch), " compound(s).", call. = FALSE)
  }
}

policy_normalize_tier <- function(values) {
  normalized <- tolower(trimws(as.character(values)))
  output <- rep(NA_character_, length(normalized))
  output[normalized %in% c("low", "low priority")] <- "Low priority"
  output[normalized %in% c("moderate", "moderate priority")] <-
    "Moderate priority"
  output[normalized %in% c("high", "high priority", "critical high")] <-
    "High priority"
  output
}

policy_derive_tier <- function(score, low_threshold, high_threshold, hazard, exposure, config) {
  derive_priority_tier_shared(score, hazard, exposure, config,
    low_threshold = low_threshold, high_threshold = high_threshold)
}

policy_wilson_interval <- function(successes, total, z) {
  if (total <= 0L || successes < 0L || successes > total) {
    stop("Wilson interval requires 0 <= successes <= total and total > 0.", call. = FALSE)
  }
  proportion <- successes / total
  denominator <- 1 + z^2 / total
  centre <- (proportion + z^2 / (2 * total)) / denominator
  half_width <- z * sqrt(
    proportion * (1 - proportion) / total + z^2 / (4 * total^2)
  ) / denominator
  c(proportion = proportion, ci_low = centre - half_width, ci_high = centre + half_width)
}

policy_odds_ratio <- function(
  successes,
  failures,
  reference_successes,
  reference_failures,
  z
) {
  cells <- c(successes, failures, reference_successes, reference_failures)
  if (any(!is.finite(cells)) || any(cells <= 0)) {
    stop(
      "Odds-ratio calculation requires four finite positive cell counts.",
      call. = FALSE
    )
  }
  log_or <- log(
    (successes / failures) /
      (reference_successes / reference_failures)
  )
  standard_error <- sqrt(
    1 / successes + 1 / failures +
      1 / reference_successes + 1 / reference_failures
  )
  c(
    odds_ratio = exp(log_or),
    or_ci_low = exp(log_or - z * standard_error),
    or_ci_high = exp(log_or + z * standard_error)
  )
}

read_policy_concordance_input <- function(snapshot, config) {
  compounds <- read_current(policy_required_fields(config), "ranked")
  keys <- toupper(trimws(compounds$Inchikey_std))
  if (nrow(compounds) != snapshot$row_count ||
      any(!nzchar(keys)) || anyDuplicated(keys)) {
    stop(
      "Policy-concordance input must preserve one full InChIKey per snapshot row.",
      call. = FALSE
    )
  }
  specs <- policy_component_specs(config)
  raw_scores <- stats::setNames(
    lapply(
      specs$score_column,
      function(column) policy_numeric(
        compounds[[column]], column, missing_as_zero = FALSE
      )
    ),
    specs$component
  )
  contributions <- stats::setNames(
    Map(function(values, multiplier) values * multiplier,
        raw_scores, specs$multiplier),
    specs$component
  )
  tolerance <- as.numeric(config$thresholds$score_tolerance)
  for (index in seq_len(nrow(specs))) {
    values <- contributions[[specs$component[[index]]]]
    if (any(values < -tolerance) ||
        max(values) > specs$theoretical_maximum[[index]] + tolerance) {
      stop(
        specs$component[[index]],
        " contribution falls outside its declared range.",
        call. = FALSE
      )
    }
  }
  contribution_frame <- as.data.frame(contributions, check.names = FALSE)
  recomputed_hazard <- rowSums(
    contribution_frame[, specs$family == "Hazard", drop = FALSE]
  )
  recomputed_exposure <- rowSums(
    contribution_frame[, specs$family == "Exposure", drop = FALSE]
  )
  recomputed_priority <- recomputed_hazard + recomputed_exposure
  reported_hazard <- policy_numeric(compounds$Hazard_score, "Hazard_score")
  reported_exposure <- policy_numeric(compounds$Exposure_score, "Exposure_score")
  reported_priority <- policy_numeric(compounds$Priority_score, "Priority_score")
  policy_assert_equal(
    recomputed_hazard, reported_hazard,
    "Recomputed Hazard_score disagrees with the stored value", tolerance
  )
  policy_assert_equal(
    recomputed_exposure, reported_exposure,
    "Recomputed Exposure_score disagrees with the stored value", tolerance
  )
  policy_assert_equal(
    recomputed_priority, reported_priority,
    "Recomputed Priority_score disagrees with the stored value", tolerance
  )
  reported_tier <- policy_normalize_tier(compounds$Priority_tier)
  derived_tier <- policy_derive_tier(
    reported_priority,
    as.numeric(config$thresholds$low_priority_upper),
    as.numeric(config$thresholds$high_priority_lower),
    reported_hazard, reported_exposure, config
  )
  if (any(is.na(reported_tier)) || any(reported_tier != derived_tier)) {
    stop("Stored and reconstructed priority tiers disagree.", call. = FALSE)
  }

  gic_status <- trimws(ifelse(
    is.na(compounds$GIC_regulatory_status),
    "",
    as.character(compounds$GIC_regulatory_status)
  ))
  allowed_gic <- as.character(unlist(
    config$allowed_gic_statuses, use.names = FALSE
  ))
  invalid_gic <- !nzchar(gic_status) | !(gic_status %in% allowed_gic)
  if (any(invalid_gic)) {
    stop(
      "GIC_regulatory_status contains ", sum(invalid_gic),
      " missing or unsupported value(s).",
      call. = FALSE
    )
  }

  list(
    keys = keys,
    name = as.character(compounds$Name_std),
    cas = as.character(compounds$CAS),
    resolution_route = as.character(compounds$resolution_route),
    source_dbs = as.character(compounds$source_dbs),
    raw_scores = raw_scores,
    contributions = contribution_frame,
    hazard_score = reported_hazard,
    exposure_score = reported_exposure,
    priority_score = reported_priority,
    priority_tier = reported_tier,
    inventory_listing_count = policy_numeric(
      compounds$Exposure_inventory_listing_count,
      "Exposure_inventory_listing_count",
      missing_as_zero = FALSE
    ),
    gic_status = gic_status,
    analytical_detectability = trimws(ifelse(
      is.na(compounds$Analytical_detectability),
      "",
      as.character(compounds$Analytical_detectability)
    )),
    specs = specs
  )
}

policy_analytical_annotation <- function(values) {
  output <- rep("Missing annotation", length(values))
  output[values == "GC-EI"] <- "GC-EI-MS"
  output[values == "RPLC +ESI"] <- "RPLC +ESI-HRMS"
  output[values == "RPLC -ESI"] <- "RPLC -ESI-HRMS"
  output[values == "NORMAN SusDat match; no platform prediction"] <-
    "NORMAN match; platform unresolved"
  output[values == "No NORMAN SusDat match"] <- "No NORMAN match"
  output
}

policy_capture_curve <- function(score, endpoint, method) {
  if (length(score) != length(endpoint) || any(!is.finite(score))) {
    stop("Capture-curve score and endpoint inputs are invalid.", call. = FALSE)
  }
  endpoint_total <- sum(endpoint)
  if (endpoint_total <= 0L) {
    stop("Capture curves require at least one endpoint-positive compound.", call. = FALSE)
  }
  ordered_scores <- sort(unique(score), decreasing = TRUE)
  group_size <- vapply(
    ordered_scores, function(value) sum(score == value), integer(1)
  )
  endpoint_count <- vapply(
    ordered_scores, function(value) sum(endpoint[score == value]), integer(1)
  )
  data.frame(
    score = c(Inf, ordered_scores),
    group_size = c(0L, group_size),
    endpoint_count = c(0L, endpoint_count),
    screened_fraction = c(0, cumsum(group_size) / length(score)),
    captured_fraction = c(0, cumsum(endpoint_count) / endpoint_total),
    method = method,
    stringsAsFactors = FALSE
  )
}

policy_interpolate_capture <- function(curve, screened_fraction) {
  stats::approx(
    x = curve$screened_fraction,
    y = curve$captured_fraction,
    xout = screened_fraction,
    ties = "ordered",
    rule = 2
  )$y
}

policy_capture_metrics <- function(curve, high_priority_fraction) {
  data.frame(
    area_under_capture_curve = sum(
      diff(curve$screened_fraction) *
        (
          head(curve$captured_fraction, -1) +
            tail(curve$captured_fraction, -1)
        ) / 2
    ),
    capture_at_10_percent = policy_interpolate_capture(curve, 0.10),
    capture_at_20_percent = policy_interpolate_capture(curve, 0.20),
    capture_at_high_priority_fraction = policy_interpolate_capture(
      curve, high_priority_fraction
    ),
    stringsAsFactors = FALSE
  )
}

prepare_policy_concordance_data <- function(input, config) {
  strong_action_statuses <- as.character(unlist(
    config$strong_action_statuses, use.names = FALSE
  ))
  inventory_contribution <- input$contributions[["Inventory presence"]]
  scenario <- function(id) score_scenario(id,input$hazard_score,input$exposure_score,input$raw_scores,inventory_contribution,input$inventory_listing_count)$score
  equal_pbmt_score <- scenario('equal_pbmt_weights')
  inventory_linear_score <- scenario('inventory_linear')
  inventory_halved_score <- scenario('inventory_halved')
  exposure_capped_score <- scenario('exposure_capped')
  is_high <- function(score, hazard, exposure, threshold) {
    derive_priority_tier_shared(score, hazard, exposure, config,
      high_threshold = threshold) == "High priority"
  }
  baseline_threshold <- as.numeric(config$thresholds$baseline_stable_minimum)
  alternative_threshold <- as.numeric(config$thresholds$alternative_stable_minimum)
  stable_high_priority <-
    is_high(input$priority_score, input$hazard_score, input$exposure_score, baseline_threshold) &
    is_high(equal_pbmt_score, equal_pbmt_score - input$exposure_score,
            input$exposure_score, alternative_threshold) &
    is_high(inventory_linear_score, input$hazard_score,
            inventory_linear_score - input$hazard_score, alternative_threshold) &
    is_high(inventory_halved_score, input$hazard_score,
            inventory_halved_score - input$hazard_score, alternative_threshold) &
    is_high(exposure_capped_score, input$hazard_score,
            pmin(input$exposure_score, 8), alternative_threshold)
  strong_action <- input$gic_status %in% strong_action_statuses
  priority_pathway <- ifelse(
    input$hazard_score >= 6 & input$exposure_score >= 6,
    "Joint hazard-exposure",
    ifelse(
      input$hazard_score >= 6,
      "Hazard-led",
      ifelse(input$exposure_score >= 6, "Exposure-led", "Other")
    )
  )
  analytical_annotation <- policy_analytical_annotation(
    input$analytical_detectability
  )
  compound_level <- data.frame(
    Inchikey_std = input$keys,
    Name_std = input$name,
    CAS = input$cas,
    resolution_route = input$resolution_route,
    source_dbs = input$source_dbs,
    Priority_score = input$priority_score,
    Hazard_score = input$hazard_score,
    Exposure_score = input$exposure_score,
    Exposure_inventory_score = inventory_contribution,
    Priority_tier = input$priority_tier,
    GIC_regulatory_status = input$gic_status,
    strong_action = strong_action,
    score_without_inventory = input$priority_score - inventory_contribution,
    equal_pbmt_score = equal_pbmt_score,
    inventory_linear_0_5_per_list_score = inventory_linear_score,
    inventory_weight_halved_score = inventory_halved_score,
    exposure_capped_at_8_score = exposure_capped_score,
    stable_high_priority = stable_high_priority,
    priority_pathway = priority_pathway,
    analytical_annotation = analytical_annotation,
    stringsAsFactors = FALSE
  )

  z <- as.numeric(config$thresholds$confidence_z)
  tier_rows <- lapply(policy_priority_levels, function(tier) {
    selected <- compound_level$Priority_tier == tier
    total <- sum(selected)
    successes <- sum(compound_level$strong_action[selected])
    interval <- policy_wilson_interval(successes, total, z)
    data.frame(
      priority_tier = tier,
      compound_count = total,
      strong_action_count = successes,
      non_strong_action_count = total - successes,
      proportion = interval[["proportion"]],
      ci_low = interval[["ci_low"]],
      ci_high = interval[["ci_high"]],
      stringsAsFactors = FALSE
    )
  })
  tier_summary <- do.call(rbind, tier_rows)
  reference <- tier_summary[tier_summary$priority_tier == "Low priority", ]
  odds_rows <- lapply(seq_len(nrow(tier_summary)), function(index) {
    row <- tier_summary[index, ]
    if (row$priority_tier == "Low priority") {
      return(c(odds_ratio = 1, or_ci_low = 1, or_ci_high = 1))
    }
    policy_odds_ratio(
      row$strong_action_count,
      row$non_strong_action_count,
      reference$strong_action_count,
      reference$non_strong_action_count,
      z
    )
  })
  tier_summary <- cbind(tier_summary, as.data.frame(do.call(rbind, odds_rows)))
  rownames(tier_summary) <- NULL

  high_priority_fraction <- mean(
    compound_level$Priority_tier == "High priority"
  )
  ranking_scores <- list(
    "Integrated score" = compound_level$Priority_score,
    "Integrated, inventory removed" = compound_level$score_without_inventory,
    "Exposure only" = compound_level$Exposure_score,
    "Hazard only" = compound_level$Hazard_score
  )
  curve_rows <- lapply(policy_method_levels, function(method) {
    policy_capture_curve(
      ranking_scores[[method]], compound_level$strong_action, method
    )
  })
  ranking_curves <- do.call(rbind, curve_rows)
  rownames(ranking_curves) <- NULL
  metric_rows <- lapply(policy_method_levels, function(method) {
    curve <- ranking_curves[ranking_curves$method == method, , drop = FALSE]
    cbind(
      data.frame(method = method, stringsAsFactors = FALSE),
      policy_capture_metrics(curve, high_priority_fraction)
    )
  })
  ranking_metrics <- do.call(rbind, metric_rows)
  rownames(ranking_metrics) <- NULL
  marker_rows <- lapply(policy_method_levels, function(method) {
    curve <- ranking_curves[ranking_curves$method == method, , drop = FALSE]
    data.frame(
      method = method,
      screened_fraction = high_priority_fraction,
      captured_fraction = policy_interpolate_capture(
        curve, high_priority_fraction
      ),
      stringsAsFactors = FALSE
    )
  })
  ranking_markers <- do.call(rbind, marker_rows)
  rownames(ranking_markers) <- NULL

  stable_outside <- compound_level[
    compound_level$stable_high_priority & !compound_level$strong_action,
    , drop = FALSE
  ]
  regulatory_context <- rep(NA_character_, nrow(stable_outside))
  regulatory_context[
    stable_outside$GIC_regulatory_status ==
      "monitoring_reporting_or_hazard_classification"
  ] <- "Monitoring/reporting or\nhazard classification"
  regulatory_context[
    stable_outside$GIC_regulatory_status ==
      "inventory_registration_or_use_only"
  ] <- "Inventory/registration/use only"
  regulatory_context[
    stable_outside$GIC_regulatory_status == "not_listed"
  ] <- "No linked GIC listing"
  if (any(is.na(regulatory_context))) {
    stop("Stable non-strong-action candidates have invalid GIC context.", call. = FALSE)
  }
  stable_outside$regulatory_context <- regulatory_context

  context_rows <- list()
  row_index <- 1L
  for (context in policy_regulatory_context_levels) {
    running_total <- 0
    context_total <- sum(stable_outside$regulatory_context == context)
    for (pathway in policy_pathway_levels) {
      count <- sum(
        stable_outside$regulatory_context == context &
          stable_outside$priority_pathway == pathway
      )
      context_rows[[row_index]] <- data.frame(
        regulatory_context = context,
        priority_pathway = pathway,
        compound_count = count,
        context_total = context_total,
        segment_midpoint = running_total + count / 2,
        stringsAsFactors = FALSE
      )
      running_total <- running_total + count
      row_index <- row_index + 1L
    }
  }
  stable_context_summary <- do.call(rbind, context_rows)
  rownames(stable_context_summary) <- NULL
  stable_context_totals <- unique(stable_context_summary[c(
    "regulatory_context", "context_total"
  )])

  not_listed_stable <- stable_outside[
    stable_outside$regulatory_context == "No linked GIC listing",
    , drop = FALSE
  ]
  if (any(not_listed_stable$analytical_annotation == "Missing annotation")) {
    stop(
      "GIC-unlisted stable candidates contain missing analytical annotations.",
      call. = FALSE
    )
  }
  not_listed_count <- nrow(not_listed_stable)
  analytical_counts <- vapply(
    policy_analytical_levels,
    function(category) sum(
      not_listed_stable$analytical_annotation == category
    ),
    integer(1)
  )
  no_match_count <- analytical_counts[["No NORMAN match"]]
  matched_count <- not_listed_count - no_match_count

  analytical_display <- data.frame(
    scope = c("All candidates", "All candidates"),
    category = c("No NORMAN match", "NORMAN match"),
    compound_count = c(no_match_count, matched_count),
    denominator = c(not_listed_count, not_listed_count),
    stringsAsFactors = FALSE
  )
  matched_categories <- setdiff(
    policy_analytical_levels,
    c("No NORMAN match", "Missing annotation")
  )
  for (category in matched_categories) {
    count <- analytical_counts[[category]]
    if (count <= 0L) {
      next
    }
    analytical_display <- rbind(
      analytical_display,
      data.frame(
        scope = "Matched subset",
        category = category,
        compound_count = count,
        denominator = matched_count,
        stringsAsFactors = FALSE
      )
    )
  }
  analytical_display$proportion <-
    ifelse(analytical_display$denominator > 0, analytical_display$compound_count / analytical_display$denominator, NA_real_)
  analytical_display$display_category <- analytical_display$category
  analytical_display$display_category[
    analytical_display$category == "No NORMAN match"
  ] <- "No SusDat match"
  analytical_display$display_category[
    analytical_display$category == "NORMAN match"
  ] <- "SusDat matched"
  analytical_display$display_category[
    analytical_display$category == "NORMAN match; platform unresolved"
  ] <- "Platform unresolved"

  stable_outside <- stable_outside[order(
    -stable_outside$Priority_score,
    -stable_outside$Hazard_score,
    -stable_outside$Exposure_score,
    stable_outside$Name_std
  ), , drop = FALSE]
  not_listed_stable <- not_listed_stable[order(
    -not_listed_stable$Priority_score,
    -not_listed_stable$Hazard_score,
    -not_listed_stable$Exposure_score,
    not_listed_stable$Name_std
  ), , drop = FALSE]

  unit_values <- c(
    tier_summary$proportion, tier_summary$ci_low, tier_summary$ci_high,
    ranking_curves$screened_fraction, ranking_curves$captured_fraction,
    ranking_metrics$capture_at_10_percent,
    ranking_metrics$capture_at_20_percent,
    ranking_metrics$capture_at_high_priority_fraction,
    analytical_display$proportion[!is.na(analytical_display$proportion)]
  )
  tolerance <- as.numeric(config$thresholds$score_tolerance)
  if (any(!is.finite(unit_values)) || any(unit_values < -tolerance) ||
      any(unit_values > 1 + tolerance)) {
    stop("Policy-concordance fractions must be finite and within [0, 1].", call. = FALSE)
  }
  if (sum(tier_summary$compound_count) != nrow(compound_level) ||
      sum(stable_context_totals$context_total) != nrow(stable_outside) ||
      sum(analytical_display$compound_count[
        analytical_display$scope == "All candidates"
      ]) != not_listed_count ||
      sum(analytical_display$compound_count[
        analytical_display$scope == "Matched subset"
      ]) != matched_count) {
    stop("Policy-concordance source tables do not conserve their populations.", call. = FALSE)
  }

  list(
    source_data = list(
      strong_action_prevalence = list(
        strong_action_prevalence = tier_summary
      ),
      ranking_capture = list(
        ranking_capture_curves = ranking_curves,
        ranking_capture_metrics = ranking_metrics,
        ranking_capture_markers = ranking_markers
      ),
      stable_review_context = list(
        stable_review_context = stable_context_summary,
        stable_review_context_totals = stable_context_totals
      ),
      analytical_annotation_gaps = list(
        analytical_annotation_gaps = analytical_display
      )
    ),
    audit_tables = list(
      compound_policy_analysis = compound_level,
      review_candidates_outside_strong_action = stable_outside,
      review_candidates_no_gic_listing = not_listed_stable
    ),
    statistics = list(
      population_total = nrow(compound_level),
      excluded_rows = lock$total - nrow(compound_level),
      strong_action_count = as.integer(sum(compound_level$strong_action)),
      high_priority_count = as.integer(sum(
        compound_level$Priority_tier == "High priority"
      )),
      high_priority_fraction = high_priority_fraction,
      stable_high_priority_count = as.integer(sum(stable_high_priority)),
      stable_outside_strong_action_count = nrow(stable_outside),
      stable_no_gic_listing_count = not_listed_count,
      stable_no_gic_listing_without_norman_match = no_match_count,
      norman_matched_count = matched_count
    )
  )
}
