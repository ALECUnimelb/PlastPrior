exposure_score_classes <- c("Score 0", "Low (0.5)", "Moderate (1)", "High (2)")

classify_exposure_score <- function(values) {
  if (any(!is.finite(values))) {
    stop("Exposure component scores cannot be missing.", call. = FALSE)
  }
  output <- rep(NA_character_, length(values))
  output[abs(values - 0) <= 1e-9] <- "Score 0"
  output[abs(values - 0.5) <= 1e-9] <- "Low (0.5)"
  output[abs(values - 1) <= 1e-9] <- "Moderate (1)"
  output[abs(values - 2) <= 1e-9] <- "High (2)"
  if (any(is.na(output))) {
    stop(
      "Exposure component scores must be 0, 0.5, 1, or 2; found ",
      paste(sort(unique(values[is.na(output)])), collapse = ", "),
      call. = FALSE
    )
  }
  output
}

build_exposure_profiles <- function(scores) {
  rows <- list()
  positive_counts <- list()
  row_index <- 1L
  for (component_order in seq_along(scores)) {
    component <- names(scores)[[component_order]]
    values <- scores[[component_order]]
    classes <- classify_exposure_score(values)
    counts <- table(factor(classes, levels = exposure_score_classes))
    positive_counts[[component]] <- sum(values > 0)
    for (class_order in seq_along(exposure_score_classes)) {
      count <- as.integer(counts[[class_order]])
      rows[[row_index]] <- data.frame(
        component = component,
        component_order = component_order,
        score_class = exposure_score_classes[[class_order]],
        score_class_order = class_order,
        compound_count = count,
        proportion = count / length(values),
        stringsAsFactors = FALSE
      )
      row_index <- row_index + 1L
    }
  }
  list(profiles = do.call(rbind, rows), positive_counts = positive_counts)
}

status_count_list <- function(compounds, specifications) {
  output <- list()
  for (component in names(specifications)) {
    columns <- specifications[[component]]
    normalized <- lapply(columns, function(column) {
      normalize_priority_text(compounds[[column]]) == "available"
    })
    available <- Reduce(`&`, normalized)
    output[[component]] <- list(
      available = sum(available),
      unavailable = sum(!available)
    )
  }
  output
}

prepare_exposure_component_profiles <- function(compounds, metadata) {
  dimension_scores <- lapply(exposure_dimensions, function(columns) {
    rowSums(compounds[, columns, drop = FALSE], na.rm = FALSE)
  })
  dimensions <- build_exposure_profiles(dimension_scores)

  indicator_scores <- lapply(exposure_indicators, function(column) compounds[[column]])
  indicators <- build_exposure_profiles(indicator_scores)

  food_positive <- compounds$Exposure_food_contact_score > 0
  human_positive <- compounds$Exposure_human_biomonitoring_score > 0
  overlap <- list(
    neither = sum(!food_positive & !human_positive),
    food_contact_only = sum(food_positive & !human_positive),
    human_biomonitoring_only = sum(!food_positive & human_positive),
    both = sum(food_positive & human_positive)
  )
  if (sum(unlist(overlap, use.names = FALSE)) != nrow(compounds)) {
    stop("Food-contact/biomonitoring overlap does not conserve compounds.", call. = FALSE)
  }

  dimension_status_columns <- exposure_indicator_status_columns
  dimension_status_columns[["Food-contact + biomonitoring"]] <- c(
    "Exposure_food_contact_data_status",
    "Exposure_FCChumon_detection_data_status"
  )
  dimension_status_columns[["Food-contact migration"]] <- NULL
  dimension_status_columns[["Human biomonitoring"]] <- NULL

  list(
    source_data = list(
      exposure_component_profiles = dimensions$profiles,
      exposure_indicator_profiles = indicators$profiles
    ),
    statistics = list(
      population_full = nrow(compounds),
      dimensions = names(exposure_dimensions),
      indicators = names(exposure_indicators),
      positive_counts = dimensions$positive_counts,
      indicator_positive_counts = indicators$positive_counts,
      food_contact_biomonitoring_overlap = overlap,
      human_biomonitoring_positive = metadata$human_biomonitoring_positive,
      food_contact_and_human_are_separate_indicators = TRUE,
      food_contact_and_human_are_joint_dimension = TRUE,
      display_classes_merge_source_availability_with_score_zero = TRUE,
      dimension_data_status_counts = status_count_list(
        compounds, dimension_status_columns
      ),
      indicator_data_status_counts = status_count_list(
        compounds, exposure_indicator_status_columns
      )
    )
  )
}
