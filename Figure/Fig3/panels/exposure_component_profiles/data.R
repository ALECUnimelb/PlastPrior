exposure_score_classes <- c("No usable evidence", "Score 0", "Low (0.5)", "Moderate (1)", "High (2)")

classify_exposure_score <- function(values) {
  output <- rep(NA_character_, length(values))
  output[!is.na(values) & abs(values - 0) <= 1e-9] <- "Score 0"
  output[!is.na(values) & abs(values - 0.5) <= 1e-9] <- "Low (0.5)"
  output[!is.na(values) & abs(values - 1) <= 1e-9] <- "Moderate (1)"
  output[!is.na(values) & abs(values - 2) <= 1e-9] <- "High (2)"
  output[is.na(values)] <- "No usable evidence"
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
    positive_counts[[component]] <- sum(values > 0, na.rm = TRUE)
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

prepare_exposure_component_profiles <- function(compounds, metadata) {
  scores <- lapply(exposure_dimensions,function(columns) rowSums(compounds[,columns,drop=FALSE],na.rm=FALSE))
  dimensions <- build_exposure_profiles(scores)
  indicators <- build_exposure_profiles(lapply(exposure_indicators,function(column) compounds[[column]]))
  stopifnot(all(tapply(dimensions$profiles$compound_count,dimensions$profiles$component,sum)==nrow(compounds)))
  list(source_data=list(exposure_component_profiles=dimensions$profiles,exposure_indicator_profiles=indicators$profiles), statistics=list(population_full=nrow(compounds),missing_is_separate_from_zero=TRUE))
}
