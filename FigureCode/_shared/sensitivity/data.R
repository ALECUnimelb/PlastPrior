priority_sensitivity_component_specs <- function(config) {
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

priority_sensitivity_required_fields <- function(config) {
  specs <- priority_sensitivity_component_specs(config)
  unique(c(
    "Inchikey_std", "Hazard_score", "Exposure_score", "Priority_score",
    "Priority_tier", "Exposure_inventory_listing_count", specs$score_column
  ))
}

priority_sensitivity_numeric <- function(
  values,
  column_name,
  missing_as_zero = FALSE
) {
  text <- trimws(ifelse(is.na(values), "", as.character(values)))
  output <- suppressWarnings(as.numeric(text))
  invalid <- nzchar(text) & (!is.finite(output) | is.na(output))
  if (any(invalid)) {
    stop(column_name, " contains invalid numeric values.", call. = FALSE)
  }
  if (!missing_as_zero && any(!nzchar(text))) {
    stop(column_name, " contains missing values.", call. = FALSE)
  }
  if (missing_as_zero) output[!nzchar(text)] <- 0 # Contribution only; source missingness is preserved.
  output
}

priority_sensitivity_assert_equal <- function(
  observed,
  expected,
  message,
  tolerance = 1e-9
) {
  mismatch <- !is.finite(observed) | !is.finite(expected) |
    abs(observed - expected) > tolerance
  if (any(mismatch)) {
    stop(message, " for ", sum(mismatch), " compound(s).", call. = FALSE)
  }
}

derive_priority_tier_sensitivity <- function(
  scores, moderate_hazard_min, high_hazard_gt, hazard, exposure, config
) {
  derive_priority_tier_shared(scores, hazard, exposure, config,
    moderate_hazard_min = moderate_hazard_min, high_hazard_gt = high_hazard_gt)
}

normalize_priority_tier_sensitivity <- function(values) {
  normalized <- tolower(trimws(as.character(values)))
  output <- rep(NA_character_, length(normalized))
  output[normalized %in% c("low", "low priority")] <- "Low priority"
  output[normalized %in% c("moderate", "moderate priority")] <-
    "Moderate priority"
  output[normalized %in% c("high", "high priority", "critical high")] <-
    "High priority"
  output
}

priority_sensitivity_jaccard <- function(reference, comparison) {
  union_count <- sum(reference | comparison)
  if (union_count == 0L) {
    return(NA_real_)
  }
  sum(reference & comparison) / union_count
}

read_priority_sensitivity_input <- function(snapshot, config) {
  compounds <- read_current(priority_sensitivity_required_fields(config), "ranked")
  if (nrow(compounds) != snapshot$row_count ||
      anyDuplicated(compounds$Inchikey_std) ||
      any(!nzchar(trimws(compounds$Inchikey_std)))) {
    stop(
      "Priority sensitivity input must preserve one full InChIKey per snapshot row.",
      call. = FALSE
    )
  }

  specs <- priority_sensitivity_component_specs(config)
  raw_scores <- stats::setNames(
    lapply(
      specs$score_column,
      function(column) priority_sensitivity_numeric(
        compounds[[column]], column, missing_as_zero = TRUE
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
  baseline_score <- rowSums(contribution_frame)
  hazard_score <- rowSums(contribution_frame[, specs$family == "Hazard", drop = FALSE])
  exposure_score <- rowSums(
    contribution_frame[, specs$family == "Exposure", drop = FALSE]
  )
  reported_priority <- priority_sensitivity_numeric(
    compounds$Priority_score, "Priority_score"
  )
  reported_hazard <- priority_sensitivity_numeric(
    compounds$Hazard_score, "Hazard_score"
  )
  reported_exposure <- priority_sensitivity_numeric(
    compounds$Exposure_score, "Exposure_score"
  )
  priority_sensitivity_assert_equal(
    baseline_score, reported_priority,
    "Reconstructed priority score disagrees with Priority_score", tolerance
  )
  priority_sensitivity_assert_equal(
    hazard_score, reported_hazard,
    "Reconstructed hazard score disagrees with Hazard_score", tolerance
  )
  priority_sensitivity_assert_equal(
    exposure_score, reported_exposure,
    "Reconstructed exposure score disagrees with Exposure_score", tolerance
  )
  if (max(baseline_score) >
      as.numeric(config$thresholds$expected_total_maximum) + tolerance) {
    stop("Priority score exceeds the declared maximum.", call. = FALSE)
  }

  baseline_tier <- derive_priority_tier_sensitivity(
    baseline_score,
    as.numeric(config$thresholds$moderate_hazard_min),
    as.numeric(config$thresholds$high_hazard_gt),
    hazard_score, exposure_score, config
  )
  reported_tier <- normalize_priority_tier_sensitivity(compounds$Priority_tier)
  if (any(is.na(reported_tier))) {
    stop("Priority_tier contains an unsupported or missing label.", call. = FALSE)
  }
  if (any(baseline_tier != reported_tier)) {
    stop("Reconstructed priority tiers disagree with Priority_tier.", call. = FALSE)
  }

  list(
    keys = compounds$Inchikey_std,
    raw_scores = raw_scores,
    contributions = contribution_frame,
    baseline_score = baseline_score,
    baseline_tier = baseline_tier,
    hazard_score = hazard_score,
    exposure_score = exposure_score,
    inventory_listing_count = priority_sensitivity_numeric(
      compounds$Exposure_inventory_listing_count,
      "Exposure_inventory_listing_count",
      missing_as_zero = TRUE
    ),
    specs = specs
  )
}

prepare_priority_sensitivity_data <- function(input, config, include_sensitivity=TRUE) {
  tolerance <- as.numeric(config$thresholds$score_tolerance)
  tiers <- priority_sensitivity_levels
  component_names <- input$specs$component
  positive <- input$contributions > tolerance
  positive_count <- rowSums(positive)
  population_total <- length(input$baseline_score)

  compound_summary <- data.frame(
    Inchikey_std = input$keys,
    Hazard_score = input$hazard_score,
    Exposure_score = input$exposure_score,
    Priority_score = input$baseline_score,
    Priority_tier = input$baseline_tier,
    positive_input_count = positive_count,
    input$contributions,
    check.names = FALSE,
    stringsAsFactors = FALSE
  )

  breadth_rows <- list()
  breadth_metric_rows <- list()
  for (tier in tiers) {
    tier_values <- positive_count[input$baseline_tier == tier]
    tier_total <- length(tier_values)
    counts <- tabulate(tier_values + 1L, nbins = length(component_names) + 1L)
    breadth_rows[[tier]] <- data.frame(
      priority_tier = tier,
      positive_input_count = 0:length(component_names),
      compound_count = counts,
      tier_total = tier_total,
      within_tier_proportion = counts / tier_total,
      stringsAsFactors = FALSE
    )
    breadth_metric_rows[[tier]] <- data.frame(
      priority_tier = tier,
      compound_count = tier_total,
      mean_positive_inputs = mean(tier_values),
      median_positive_inputs = stats::median(tier_values),
      q1_positive_inputs = as.numeric(stats::quantile(tier_values, 0.25)),
      q3_positive_inputs = as.numeric(stats::quantile(tier_values, 0.75)),
      stringsAsFactors = FALSE
    )
  }
  breadth <- do.call(rbind, breadth_rows)
  rownames(breadth) <- NULL
  breadth_metrics <- do.call(rbind, breadth_metric_rows)
  rownames(breadth_metrics) <- NULL

  prevalence_rows <- list()
  row_id <- 1L
  for (tier in tiers) {
    tier_rows <- input$baseline_tier == tier
    tier_total <- sum(tier_rows)
    for (index in seq_along(component_names)) {
      positive_compounds <- sum(positive[tier_rows, index])
      prevalence_rows[[row_id]] <- data.frame(
        priority_tier = tier,
        component = component_names[[index]],
        family = input$specs$family[[index]],
        tier_total = tier_total,
        positive_compounds = positive_compounds,
        positive_proportion = positive_compounds / tier_total,
        stringsAsFactors = FALSE
      )
      row_id <- row_id + 1L
    }
  }
  prevalence <- do.call(rbind, prevalence_rows)
  rownames(prevalence) <- NULL

  if (!include_sensitivity) return(list(
    source_data=list(positive_input_breadth=list(positive_input_breadth=breadth,positive_input_breadth_metrics=breadth_metrics),positive_input_prevalence=list(positive_input_prevalence=prevalence)),
    audit_tables=list(compound_input_summary=compound_summary),
    statistics=list(population_total=population_total,excluded_rows=lock$total-population_total,tier_counts=as.list(table(input$baseline_tier)))))
  baseline_high <- input$baseline_tier == "High priority"
  if (!any(baseline_high)) {
    stop("Sensitivity analysis requires at least one high-priority compound.", call. = FALSE)
  }
  leave_rows <- lapply(seq_along(component_names), function(index) {
    component <- component_names[[index]]
    perturbed_score <- input$baseline_score - input$contributions[[component]]
    removed <- input$contributions[[component]]
    hazard <- input$hazard_score - if (input$specs$family[[index]] == "Hazard") removed else 0
    exposure <- input$exposure_score - if (input$specs$family[[index]] == "Exposure") removed else 0
    perturbed_tier <- derive_priority_tier_sensitivity(
      perturbed_score,
      as.numeric(config$thresholds$moderate_hazard_min),
      as.numeric(config$thresholds$high_hazard_gt),
      hazard, exposure, config
    )
    perturbed_high <- perturbed_tier == "High priority"
    rank_spearman <- suppressWarnings(stats::cor(
      input$baseline_score, perturbed_score, method = "spearman"
    ))
    data.frame(
      component = component,
      family = input$specs$family[[index]],
      removed_maximum_points = input$specs$theoretical_maximum[[index]],
      rank_spearman = rank_spearman,
      tier_agreement = mean(perturbed_tier == input$baseline_tier),
      high_priority_retention = mean(perturbed_high[baseline_high]),
      high_priority_jaccard = priority_sensitivity_jaccard(
        baseline_high, perturbed_high
      ),
      changed_tier_count = sum(perturbed_tier != input$baseline_tier),
      retained_high_count = sum(perturbed_high & baseline_high),
      perturbed_high_count = sum(perturbed_high),
      stringsAsFactors = FALSE
    )
  })
  leave_one_out <- do.call(rbind, leave_rows)
  leave_one_out <- leave_one_out[
    order(leave_one_out$high_priority_retention, leave_one_out$rank_spearman),
    , drop = FALSE
  ]
  rownames(leave_one_out) <- NULL

  inventory_component <- input$contributions[["Inventory presence"]]
  scenario_rows <- lapply(config$scenarios, function(scenario) {
    scenario_values <- score_scenario(scenario$scenario_id,input$hazard_score,input$exposure_score,input$raw_scores,inventory_component,input$inventory_listing_count)
    score <- scenario_values$score; hazard <- scenario_values$hazard; exposure <- scenario_values$exposure
    perturbed_tier <- derive_priority_tier_sensitivity(
      score,
      as.numeric(scenario$moderate_hazard_min),
      as.numeric(scenario$high_hazard_gt),
      hazard, exposure, config
    )
    perturbed_high <- perturbed_tier == "High priority"
    data.frame(
      scenario_id = scenario$scenario_id,
      scenario = scenario$label,
      note = scenario$note,
      moderate_hazard_min = as.numeric(scenario$moderate_hazard_min),
      high_hazard_gt = as.numeric(scenario$high_hazard_gt),
      rank_spearman = suppressWarnings(stats::cor(
        input$baseline_score, score, method = "spearman"
      )),
      tier_agreement = mean(perturbed_tier == input$baseline_tier),
      high_priority_retention = mean(perturbed_high[baseline_high]),
      high_priority_jaccard = priority_sensitivity_jaccard(
        baseline_high, perturbed_high
      ),
      changed_tier_count = sum(perturbed_tier != input$baseline_tier),
      perturbed_high_count = sum(perturbed_high),
      stringsAsFactors = FALSE
    )
  })
  scenario_sensitivity <- do.call(rbind, scenario_rows)
  rownames(scenario_sensitivity) <- NULL

  similarity_columns <- c(
    "rank_spearman", "tier_agreement", "high_priority_retention",
    "high_priority_jaccard"
  )
  similarity_values <- c(
    unlist(leave_one_out[similarity_columns], use.names = FALSE),
    unlist(scenario_sensitivity[similarity_columns], use.names = FALSE)
  )
  if (any(!is.finite(similarity_values)) ||
      any(similarity_values < -tolerance) ||
      any(similarity_values > 1 + tolerance)) {
    stop("Sensitivity similarity metrics must be finite and within [0, 1].", call. = FALSE)
  }
  breadth_totals <- vapply(
    tiers,
    function(tier) sum(breadth$compound_count[breadth$priority_tier == tier]),
    numeric(1)
  )
  expected_tier_totals <- as.integer(
    table(factor(input$baseline_tier, levels = tiers))
  )
  if (sum(breadth$compound_count) != population_total ||
      any(breadth_totals != expected_tier_totals)) {
    stop("Positive-input breadth does not conserve the population.", call. = FALSE)
  }

  tier_counts <- table(factor(input$baseline_tier, levels = tiers))
  worst_leave <- leave_one_out[["component"]][[1]]
  list(
    source_data = list(
      positive_input_breadth = list(
        positive_input_breadth = breadth,
        positive_input_breadth_metrics = breadth_metrics
      ),
      positive_input_prevalence = list(
        positive_input_prevalence = prevalence
      ),
      leave_one_input_out = list(
        leave_one_input_out = leave_one_out
      ),
      scenario_sensitivity = list(
        scenario_sensitivity = scenario_sensitivity
      )
    ),
    audit_tables = list(compound_input_summary = compound_summary),
    statistics = list(
      population_total = population_total,
      excluded_rows = lock$total - population_total,
      tier_counts = stats::setNames(as.list(as.integer(tier_counts)), tiers),
      baseline_high_count = as.integer(sum(baseline_high)),
      worst_leave_one_out_component = worst_leave,
      minimum_leave_one_out_high_priority_retention =
        min(leave_one_out$high_priority_retention),
      minimum_scenario_rank_spearman = min(scenario_sensitivity$rank_spearman),
      minimum_scenario_tier_agreement = min(scenario_sensitivity$tier_agreement),
      minimum_scenario_high_priority_jaccard =
        min(scenario_sensitivity$high_priority_jaccard)
    )
  )
}
