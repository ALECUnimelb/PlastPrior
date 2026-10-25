hazard_components <- c(
  Persistence = "Persistence_score",
  Bioaccumulation = "Bioaccumulation_score",
  Mobility = "Mobility_score",
  Toxicity = "Toxicity_score"
)

exposure_indicators <- c(
  "Inventory presence" = "Exposure_inventory_score",
  "Production / market" = "Exposure_production_score",
  Patents = "Exposure_patent_score",
  Literature = "Exposure_literature_score",
  "Food-contact migration" = "Exposure_food_contact_score",
  "Human biomonitoring" = "Exposure_human_biomonitoring_score"
)

exposure_dimensions <- list(
  "Inventory presence" = "Exposure_inventory_score",
  "Production / market" = "Exposure_production_score",
  Patents = "Exposure_patent_score",
  Literature = "Exposure_literature_score",
  "Food-contact + biomonitoring" = c(
    "Exposure_food_contact_score", "Exposure_human_biomonitoring_score"
  )
)

exposure_indicator_status_columns <- list(
  "Inventory presence" = "Exposure_inventory_data_status",
  "Production / market" = "Exposure_production_data_status",
  Patents = "Exposure_patent_data_status",
  Literature = "Exposure_literature_data_status",
  "Food-contact migration" = "Exposure_food_contact_data_status",
  "Human biomonitoring" = "Exposure_FCChumon_detection_data_status"
)

regulatory_status_map <- c(
  prohibited_or_phaseout = "Prohibited/phase-out",
  restricted_or_authorisation_required = "Restricted/authorisation",
  candidate_or_high_concern = "Candidate/high concern",
  monitoring_reporting_or_hazard_classification = "Monitoring/reporting/hazard",
  inventory_registration_or_use_only = "Inventory/registration/use",
  auxiliary_identifier_only = "No matched GIC listing",
  not_listed = "No matched GIC listing"
)

priority_required_columns <- function() {
  unique(c(
    "Inchikey_std",
    "Priority_score",
    "Priority_tier",
    "Hazard_score",
    "Exposure_score",
    "GIC_regulatory_status",
    unname(hazard_components),
    unname(exposure_indicators),
    "Exposure_scale_has_numeric",
    "Exposure_scale_value_tonnes",
    "Exposure_scale_market_presence",
    "Exposure_patent_count",
    "Exposure_literature_count",
    "Exposure_pubmed_title_abstract_count",
    "Exposure_inventory_listing_count",
    "Exposure_FCCmigex_listed",
    "Exposure_FCChumon_S1_detected",
    "Exposure_FCChumon_S2_detected",
    "Exposure_patent_source",
    "Exposure_literature_source",
    "Exposure_patent_policy",
    "Exposure_literature_policy",
    "Exposure_FCChumon_detection_policy",
    unname(unlist(exposure_indicator_status_columns, use.names = FALSE))
  ))
}

priority_optional_columns <- c(
  "Priority_data_status", "Hazard_data_status", "Exposure_data_status"
)

normalize_priority_text <- function(values) {
  tolower(trimws(ifelse(is.na(values), "", as.character(values))))
}

as_numeric_checked <- function(values, column_name, allow_missing = TRUE) {
  text <- trimws(ifelse(is.na(values), "", as.character(values)))
  numeric <- suppressWarnings(as.numeric(text))
  invalid <- nzchar(text) & (!is.finite(numeric) | is.na(numeric))
  if (any(invalid)) {
    stop(
      column_name, " contains ", sum(invalid), " invalid numeric value(s).",
      call. = FALSE
    )
  }
  if (!allow_missing && any(!nzchar(text))) {
    stop(column_name, " contains missing values.", call. = FALSE)
  }
  numeric
}

assert_vectors_equal <- function(observed, expected, message, tolerance = 1e-8) {
  same_missing <- is.na(observed) == is.na(expected)
  comparable <- !is.na(observed) & !is.na(expected)
  equal_numeric <- rep(TRUE, length(observed))
  equal_numeric[comparable] <- abs(observed[comparable] - expected[comparable]) <= tolerance
  if (!all(same_missing & equal_numeric)) {
    stop(message, " for ", sum(!(same_missing & equal_numeric)), " compound(s).", call. = FALSE)
  }
}

score_from_thresholds <- function(values, thresholds, scores) {
  output <- rep(0, length(values))
  finite_nonnegative <- is.finite(values) & values >= 0
  for (index in seq_along(thresholds)) {
    output[finite_nonnegative & values >= thresholds[[index]]] <- scores[[index]]
  }
  output
}

expected_inventory_score <- function(counts, statuses) {
  scores <- score_from_thresholds(counts, c(1, 2, 4), c(0.5, 1, 2))
  scores[normalize_priority_text(statuses) != "available"] <- 0
  scores
}

expected_production_score <- function(values, presence) {
  normalized_presence <- normalize_priority_text(presence)
  positive_presence <- normalized_presence %in% c(
    "confirmed_positive_quantity",
    "confirmed_confidential_quantity",
    "confirmed_record_no_public_quantity",
    "historical_record"
  )
  output <- ifelse(positive_presence, 0.5, 0)
  valid <- is.finite(values) & values >= 0
  output[valid & values > 0] <- 0.5
  output[valid & values >= 1000] <- 1
  output[valid & values >= 100000] <- 2
  output
}

expected_production_available <- function(values, presence) {
  normalized_presence <- normalize_priority_text(presence)
  available_presence <- normalized_presence %in% c(
    "confirmed_positive_quantity",
    "confirmed_confidential_quantity",
    "confirmed_record_no_public_quantity",
    "historical_record",
    "confirmed_zero_quantity"
  )
  (is.finite(values) & values >= 0) | available_presence
}

expected_patent_score <- function(counts) {
  score_from_thresholds(counts, c(1, 1000, 10000), c(0.5, 1, 2))
}

expected_literature_score <- function(counts) {
  score_from_thresholds(counts, c(1, 5, 20), c(0.5, 1, 2))
}

derive_priority_tier_r <- function(scores, statuses, config, hazard, exposure) {
  derive_priority_tier_shared(scores, hazard, exposure, config, statuses)
}

normalize_regulatory_status_r <- function(values) {
  normalized <- normalize_priority_text(values)
  normalized[!nzchar(normalized)] <- "not_listed"
  unknown <- setdiff(unique(normalized), names(regulatory_status_map))
  if (length(unknown) > 0L) {
    stop(
      "Unsupported GIC regulatory status value(s): ",
      paste(sort(unknown), collapse = ", "),
      call. = FALSE
    )
  }
  unname(regulatory_status_map[normalized])
}

validate_formal_policy <- function(values, expected, label) {
  observed <- unique(trimws(as.character(values[!is.na(values)])))
  observed <- observed[nzchar(observed)]
  if (length(observed) != 1L || !identical(observed[[1]], expected) || any(is.na(values))) {
    stop(
      label, " must be complete and equal to '", expected, "'.",
      call. = FALSE
    )
  }
}

read_priority_landscape_input <- function(snapshot, config) {
  required <- priority_required_columns()
  available <- unique(c(
    as.character(unlist(
      snapshot$manifest$priority_table$columns,
      use.names = FALSE
    )),
    as.character(unlist(
      snapshot$manifest$compound_csv_columns,
      use.names = FALSE
    ))
  ))
  selected <- c(required, intersect(priority_optional_columns, available))
  compounds <- read_analysis_snapshot_fields_r(snapshot, selected)
  if (nrow(compounds) != snapshot$row_count) {
    stop("Figure input row count changed after snapshot validation.", call. = FALSE)
  }

  numeric_columns <- unique(c(
    "Priority_score", "Hazard_score", "Exposure_score",
    unname(hazard_components), unname(exposure_indicators),
    "Exposure_scale_has_numeric", "Exposure_scale_value_tonnes",
    "Exposure_patent_count", "Exposure_literature_count",
    "Exposure_pubmed_title_abstract_count", "Exposure_inventory_listing_count",
    "Exposure_FCCmigex_listed", "Exposure_FCChumon_S1_detected",
    "Exposure_FCChumon_S2_detected"
  ))
  nonmissing_numeric <- unique(c(
    unname(exposure_indicators)
  ))
  for (column in numeric_columns) {
    compounds[[column]] <- as_numeric_checked(
      compounds[[column]], column, allow_missing = !(column %in% nonmissing_numeric)
    )
  }

  score_levels <- c(0, 0.5, 1, 2)
  for (column in unname(exposure_indicators)) {
    unsupported <- !vapply(
      compounds[[column]],
      function(value) {
        !is.na(value) && any(abs(value - score_levels) <= 1e-9)
      },
      logical(1)
    )
    if (any(unsupported)) {
      stop(column, " contains scores outside 0, 0.5, 1, and 2.", call. = FALSE)
    }
  }

  usable <- is.finite(compounds$Priority_score) &
    is.finite(compounds$Hazard_score) &
    is.finite(compounds$Exposure_score)
  assert_vectors_equal(
    compounds$Priority_score[usable],
    compounds$Hazard_score[usable] + compounds$Exposure_score[usable],
    "Priority_score disagrees with Hazard_score + Exposure_score"
  )

  expected_tier <- derive_priority_tier_r(
    compounds$Priority_score,
    if ("Priority_data_status" %in% names(compounds)) compounds$Priority_data_status else NULL,
    config, compounds$Hazard_score, compounds$Exposure_score
  )
  observed_tier <- trimws(compounds$Priority_tier)
  tier_mismatch <- is.na(observed_tier) | is.na(expected_tier) |
    observed_tier != expected_tier
  if (any(tier_mismatch)) {
    stop(
      "Priority_tier disagrees with the prespecified thresholds for ",
      sum(tier_mismatch), " compound(s).",
      call. = FALSE
    )
  }

  validate_formal_policy(
    compounds$Exposure_FCChumon_detection_policy,
    config$formal_policies$human_biomonitoring,
    "FCChumon human-biomonitoring policy"
  )
  validate_formal_policy(
    compounds$Exposure_literature_policy,
    config$formal_policies$literature,
    "Literature policy"
  )
  validate_formal_policy(
    compounds$Exposure_patent_policy,
    config$formal_policies$patent,
    "Patent policy"
  )

  expected_inventory <- expected_inventory_score(
    compounds$Exposure_inventory_listing_count,
    compounds$Exposure_inventory_data_status
  )
  assert_vectors_equal(
    compounds$Exposure_inventory_score, expected_inventory,
    "Inventory scores disagree with the 1/2/4-list thresholds"
  )

  has_numeric <- ifelse(
    is.na(compounds$Exposure_scale_has_numeric),
    FALSE,
    compounds$Exposure_scale_has_numeric != 0
  )
  value_available <- !is.na(compounds$Exposure_scale_value_tonnes)
  if (!identical(has_numeric, value_available)) {
    stop("Production numeric flag disagrees with selected quantity availability.", call. = FALSE)
  }
  expected_production <- expected_production_score(
    compounds$Exposure_scale_value_tonnes,
    compounds$Exposure_scale_market_presence
  )
  assert_vectors_equal(
    compounds$Exposure_production_score, expected_production,
    "Production scores disagree with the evidence-aware thresholds"
  )
  production_available <- expected_production_available(
    compounds$Exposure_scale_value_tonnes,
    compounds$Exposure_scale_market_presence
  )
  if (!identical(
    normalize_priority_text(compounds$Exposure_production_data_status) == "available",
    production_available
  )) {
    stop("Production availability disagrees with numeric or qualitative evidence.", call. = FALSE)
  }

  assert_vectors_equal(
    compounds$Exposure_patent_score,
    expected_patent_score(compounds$Exposure_patent_count),
    "Patent scores disagree with the 1/1,000/10,000 thresholds"
  )
  patent_source_present <- nzchar(trimws(ifelse(
    is.na(compounds$Exposure_patent_source), "", compounds$Exposure_patent_source
  )))
  if (!identical(
    normalize_priority_text(compounds$Exposure_patent_data_status) == "available",
    patent_source_present
  )) {
    stop("Patent availability disagrees with selected-source provenance.", call. = FALSE)
  }

  assert_vectors_equal(
    compounds$Exposure_literature_score,
    expected_literature_score(compounds$Exposure_literature_count),
    "Literature scores disagree with the 1/5/20 PubMed thresholds"
  )
  if (any(compounds$Exposure_literature_source != "NCBI PubMed Title/Abstract")) {
    stop("Literature source must be NCBI PubMed Title/Abstract.", call. = FALSE)
  }
  literature_available <- normalize_priority_text(
    compounds$Exposure_literature_data_status
  ) == "available"
  if (any(is.na(compounds$Exposure_pubmed_title_abstract_count[literature_available]))) {
    stop("Available Literature rows must retain a PubMed query count.", call. = FALSE)
  }
  assert_vectors_equal(
    compounds$Exposure_literature_count[literature_available],
    compounds$Exposure_pubmed_title_abstract_count[literature_available],
    "Formal Literature counts disagree with PubMed query counts"
  )

  expected_food <- as.numeric(ifelse(
    is.na(compounds$Exposure_FCCmigex_listed),
    FALSE,
    compounds$Exposure_FCCmigex_listed != 0
  ))
  assert_vectors_equal(
    compounds$Exposure_food_contact_score, expected_food,
    "Food-contact scores disagree with FCCmigex listing evidence"
  )
  detected_s1 <- ifelse(
    is.na(compounds$Exposure_FCChumon_S1_detected),
    FALSE,
    compounds$Exposure_FCChumon_S1_detected != 0
  )
  detected_s2 <- ifelse(
    is.na(compounds$Exposure_FCChumon_S2_detected),
    FALSE,
    compounds$Exposure_FCChumon_S2_detected != 0
  )
  expected_human <- as.numeric(detected_s1 | detected_s2)
  assert_vectors_equal(
    compounds$Exposure_human_biomonitoring_score, expected_human,
    "Human-biomonitoring scores disagree with strict detections"
  )

  expected_exposure <- rowSums(compounds[, unname(exposure_indicators)], na.rm = FALSE)
  assert_vectors_equal(
    compounds$Exposure_score, expected_exposure,
    "Exposure_score disagrees with the six audited indicator scores"
  )

  compounds$Priority_tier <- expected_tier
  compounds$GIC_regulatory_status_display <- normalize_regulatory_status_r(
    compounds$GIC_regulatory_status
  )
  compounds
}

priority_landscape_metadata <- function(compounds) {
  tier_counts <- table(factor(compounds$Priority_tier, levels = priority_levels))
  list(
    population_full = nrow(compounds),
    unique_full_inchikeys = length(unique(compounds$Inchikey_std)),
    priority_score_min = min(compounds$Priority_score, na.rm = TRUE),
    priority_score_max = max(compounds$Priority_score, na.rm = TRUE),
    priority_score_median = stats::median(compounds$Priority_score, na.rm = TRUE),
    hazard_score_max = max(compounds$Hazard_score, na.rm = TRUE),
    exposure_score_max = max(compounds$Exposure_score, na.rm = TRUE),
    priority_tier_counts = as.list(stats::setNames(as.integer(tier_counts), names(tier_counts))),
    human_biomonitoring_positive = sum(
      compounds$Exposure_human_biomonitoring_score > 0, na.rm = TRUE
    ),
    food_contact_positive = sum(
      compounds$Exposure_food_contact_score > 0, na.rm = TRUE
    )
  )
}
