pbmt_dimension_schema <- list(
  toxicity = list(
    label = "Toxicity",
    order = 1L,
    final_score_field = "Toxicity_score",
    basis_field = "Toxicity_score_basis",
    evidence_field = "Toxicity_evidence",
    computational_json_path = "$.qsar_toxicity.selected.score",
    plastchem_json_path = "$.curated_db.selected.score",
    final_json_path = "$.final_selection.selected.score"
  ),
  bioaccumulation = list(
    label = "Bioaccumulation",
    order = 2L,
    final_score_field = "Bioaccumulation_score",
    basis_field = "Bioaccumulation_score_basis",
    evidence_field = "Bioaccumulation_evidence",
    computational_json_path = "$.qsar_bcf_models.selected.bioaccumulation_score",
    plastchem_json_path = "$.curated_db.selected.score",
    final_json_path = "$.final_selection.selected.score"
  ),
  mobility = list(
    label = "Mobility",
    order = 3L,
    final_score_field = "Mobility_score",
    basis_field = "Mobility_score_basis",
    evidence_field = "Mobility_evidence",
    computational_json_path = "$.final_mobility.independent_score",
    plastchem_json_path = "$.curated_db.selected.score",
    final_json_path = "$.final_mobility.score"
  ),
  persistence = list(
    label = "Persistence",
    order = 4L,
    final_score_field = "Persistence_score",
    basis_field = "Persistence_score_basis",
    evidence_field = "Persistence_evidence",
    computational_json_path = "$.final_selection.independent_candidate.score",
    plastchem_json_path = "$.curated_db.selected.score",
    final_json_path = "$.final_selection.selected.score"
  )
)

pbmt_required_snapshot_fields <- function() {
  unique(c(
    "Inchikey_std",
    vapply(pbmt_dimension_schema, function(item) item$final_score_field, character(1)),
    vapply(pbmt_dimension_schema, function(item) item$basis_field, character(1)),
    vapply(pbmt_dimension_schema, function(item) item$evidence_field, character(1))
  ))
}

pbmt_numeric <- function(values, column_name) {
  text <- trimws(ifelse(is.na(values), "", as.character(values)))
  output <- suppressWarnings(as.numeric(text))
  invalid <- nzchar(text) & (!is.finite(output) | is.na(output))
  if (any(invalid)) {
    stop(column_name, " contains invalid numeric values.", call. = FALSE)
  }
  output
}

pbmt_assert_vectors_equal <- function(observed, expected, message, tolerance = 1e-9) {
  same_missing <- is.na(observed) == is.na(expected)
  comparable <- !is.na(observed) & !is.na(expected)
  same_value <- rep(TRUE, length(observed))
  same_value[comparable] <- abs(observed[comparable] - expected[comparable]) <= tolerance
  mismatch <- !(same_missing & same_value)
  if (any(mismatch)) {
    stop(message, " for ", sum(mismatch), " compound(s).", call. = FALSE)
  }
}

pbmt_agreement_band <- function(difference, config) {
  exact_tolerance <- as.numeric(config$thresholds$exact_tolerance)
  near_max <- as.numeric(config$thresholds$near_difference_max)
  moderate_max <- as.numeric(config$thresholds$moderate_difference_max)
  output <- rep(NA_character_, length(difference))
  present <- !is.na(difference)
  output[present & difference <= exact_tolerance] <- "Exact"
  output[present & difference > exact_tolerance & difference <= near_max] <-
    "Near non-exact (<=0.5)"
  output[present & difference > near_max & difference <= moderate_max] <-
    "Moderate (0.5-1)"
  output[present & difference > moderate_max] <- "Large (>1)"
  factor(output, levels = pbmt_agreement_levels)
}

read_pbmt_concordance_input <- function(snapshot, config) {
  compounds <- read_current(pbmt_required_snapshot_fields())
  stopifnot(nrow(compounds)==snapshot$row_count, !anyDuplicated(compounds$Inchikey_std))
  columns <- c('inchikey AS inchikey_std')
  for (id in names(pbmt_dimension_schema)) {
    item <- pbmt_dimension_schema[[id]]
    paths <- c(computational_score=item$computational_json_path, plastchem_score=item$plastchem_json_path, selected_final_score=item$final_json_path)
    for (name in names(paths)) columns <- c(columns, paste0('json_extract(',item$evidence_field,', ',DBI::dbQuoteString(db,paths[[name]]),') AS ',id,'_',name))
  }
  evidence <- DBI::dbGetQuery(db,paste('SELECT',paste(columns,collapse=','),'FROM compounds ORDER BY inchikey'))
  stopifnot(identical(compounds$Inchikey_std,evidence$inchikey_std))

  long_tables <- list()
  for (dimension_id in names(pbmt_dimension_schema)) {
    item <- pbmt_dimension_schema[[dimension_id]]
    computational <- pbmt_numeric(
      evidence[[paste0(dimension_id, "_computational_score")]],
      paste0(dimension_id, " computational score")
    )
    plastchem <- pbmt_numeric(
      evidence[[paste0(dimension_id, "_plastchem_score")]],
      paste0(dimension_id, " PlastChem score")
    )
    selected_final <- pbmt_numeric(
      evidence[[paste0(dimension_id, "_selected_final_score")]],
      paste0(dimension_id, " selected final score")
    )
    stored_final <- pbmt_numeric(
      compounds[[item$final_score_field]], item$final_score_field
    )
    computational <- assert_discrete_numeric(
      computational, pbmt_computational_score_levels,
      paste0(dimension_id, " computational score"), allow_missing = TRUE
    )
    plastchem <- assert_discrete_numeric(
      plastchem, pbmt_plastchem_score_levels,
      paste0(dimension_id, " PlastChem score"), allow_missing = TRUE
    )
    selected_final <- assert_discrete_numeric(
      selected_final, pbmt_plastchem_score_levels,
      paste0(dimension_id, " selected final score"), allow_missing = TRUE
    )
    stored_final <- assert_discrete_numeric(
      stored_final, pbmt_plastchem_score_levels,
      item$final_score_field, allow_missing = TRUE
    )
    pbmt_assert_vectors_equal(
      stored_final,
      selected_final,
      paste0(item$label, " stored final score disagrees with selected evidence")
    )
    has_computational <- !is.na(computational)
    has_plastchem <- !is.na(plastchem)
    coverage_category <- ifelse(
      has_computational & has_plastchem, "Shared",
      ifelse(
        has_computational, "Independent only",
        ifelse(has_plastchem, "PlastChem only", "Neither")
      )
    )
    comparison_status <- ifelse(
      has_computational & has_plastchem, "Shared",
      ifelse(
        has_computational, "Independent only",
        ifelse(has_plastchem, "PlastChem only", "Neither")
      )
    )
    delta <- computational - plastchem
    absolute_difference <- abs(delta)
    long_tables[[dimension_id]] <- data.frame(
      Inchikey_std = compounds$Inchikey_std,
      dimension_id = dimension_id,
      dimension = item$label,
      dimension_order = item$order,
      method_label = pbmt_dimension_config(config, dimension_id)$method_label,
      computational_score = computational,
      plastchem_score = plastchem,
      selected_final_score = selected_final,
      stored_final_score = stored_final,
      final_score_basis = compounds[[item$basis_field]],
      coverage_category = coverage_category,
      comparison_status = comparison_status,
      delta = delta,
      absolute_difference = absolute_difference,
      agreement_band = as.character(pbmt_agreement_band(absolute_difference, config)),
      primary_comparison_source_category = ifelse(
        has_computational,
        "Computational comparison available",
        ifelse(
          has_plastchem,
          "PlastChem-only comparison",
          "Neither primary comparison side"
        )
      ),
      stringsAsFactors = FALSE
    )
  }
  output <- do.call(rbind, long_tables)
  rownames(output) <- NULL
  if (nrow(output) != snapshot$row_count * length(pbmt_dimension_schema)) {
    stop("PBMT long-form table does not conserve the snapshot population.", call. = FALSE)
  }
  output$dimension <- factor(output$dimension, levels = pbmt_dimension_levels)
  output$coverage_category <- factor(
    output$coverage_category, levels = pbmt_coverage_levels
  )
  output$agreement_band <- factor(
    output$agreement_band, levels = pbmt_agreement_levels
  )
  output
}

pbmt_count_complete <- function(values, levels, name) {
  observed <- table(factor(values, levels = levels), useNA = "no")
  data.frame(
    setNames(list(names(observed)), name),
    count = as.integer(observed),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

prepare_pbmt_source_data <- function(compounds, snapshot, config) {
  population_total <- snapshot$row_count
  coverage_rows <- list()
  coverage_metrics_rows <- list()
  agreement_rows <- list()
  agreement_metrics_rows <- list()
  matrix_rows <- list()
  status_rows <- list()
  source_rows <- list()

  for (dimension_id in names(pbmt_dimension_schema)) {
    item <- pbmt_dimension_schema[[dimension_id]]
    subset <- compounds[compounds$dimension_id == dimension_id, , drop = FALSE]
    if (nrow(subset) != population_total) {
      stop(item$label, " does not conserve the population.", call. = FALSE)
    }
    has_computational <- !is.na(subset$computational_score)
    has_plastchem <- !is.na(subset$plastchem_score)
    shared <- has_computational & has_plastchem
    shared_n <- sum(shared)

    coverage <- pbmt_count_complete(
      as.character(subset$coverage_category), pbmt_coverage_levels, "category"
    )
    coverage$dimension_id <- dimension_id
    coverage$dimension <- item$label
    coverage$dimension_order <- item$order
    coverage$fraction <- coverage$count / population_total
    coverage_rows[[dimension_id]] <- coverage[, c(
      "dimension_id", "dimension", "dimension_order", "category", "count", "fraction"
    )]
    coverage_metrics_rows[[dimension_id]] <- data.frame(
      dimension_id = dimension_id,
      dimension = item$label,
      dimension_order = item$order,
      population_total = population_total,
      computational_total = sum(has_computational),
      computational_fraction = sum(has_computational) / population_total,
      plastchem_total = sum(has_plastchem),
      plastchem_fraction = sum(has_plastchem) / population_total,
      shared_count = shared_n,
      stringsAsFactors = FALSE
    )

    agreement <- pbmt_count_complete(
      as.character(subset$agreement_band[shared]), pbmt_agreement_levels,
      "agreement_band"
    )
    agreement$dimension_id <- dimension_id
    agreement$dimension <- item$label
    agreement$dimension_order <- item$order
    agreement$shared_n <- shared_n
    agreement$fraction_of_shared <- if (shared_n > 0L) agreement$count / shared_n else 0
    agreement_rows[[dimension_id]] <- agreement[, c(
      "dimension_id", "dimension", "dimension_order", "agreement_band",
      "count", "fraction_of_shared", "shared_n"
    )]
    shared_delta <- subset$delta[shared]
    shared_abs <- subset$absolute_difference[shared]
    agreement_metrics_rows[[dimension_id]] <- data.frame(
      dimension_id = dimension_id,
      dimension = item$label,
      dimension_order = item$order,
      shared_n = shared_n,
      mean_absolute_difference = if (shared_n > 0L) mean(shared_abs) else NA_real_,
      computational_higher_count = sum(shared_delta > 0),
      equal_count = sum(abs(shared_delta) <= as.numeric(config$thresholds$exact_tolerance)),
      plastchem_higher_count = sum(shared_delta < 0),
      stringsAsFactors = FALSE
    )

    grid <- expand.grid(
      plastchem_score = pbmt_plastchem_score_levels,
      computational_score = pbmt_computational_score_levels,
      KEEP.OUT.ATTRS = FALSE,
      stringsAsFactors = FALSE
    )
    pairs <- paste(subset$plastchem_score[shared], subset$computational_score[shared], sep = "|")
    grid_keys <- paste(grid$plastchem_score, grid$computational_score, sep = "|")
    pair_counts <- table(factor(pairs, levels = grid_keys))
    grid$count <- as.integer(pair_counts)
    grid$fraction_of_shared <- if (shared_n > 0L) grid$count / shared_n else 0
    grid$shared_n <- shared_n
    grid$exact_cell <- abs(grid$plastchem_score - grid$computational_score) <=
      as.numeric(config$thresholds$exact_tolerance)
    grid$dimension_id <- dimension_id
    grid$dimension <- item$label
    grid$dimension_order <- item$order
    matrix_rows[[dimension_id]] <- grid[, c(
      "dimension_id", "dimension", "dimension_order", "plastchem_score",
      "computational_score", "count", "fraction_of_shared", "shared_n", "exact_cell"
    )]

    status <- pbmt_count_complete(
      subset$comparison_status, pbmt_coverage_levels, "comparison_status"
    )
    status$dimension_id <- dimension_id
    status$dimension <- item$label
    status$dimension_order <- item$order
    status_rows[[dimension_id]] <- status[, c(
      "dimension_id", "dimension", "dimension_order", "comparison_status", "count"
    )]

    sources <- pbmt_count_complete(
      subset$primary_comparison_source_category,
      c(
        "Computational comparison available",
        "PlastChem-only comparison",
        "Neither primary comparison side"
      ),
      "comparison_source_category"
    )
    sources$dimension_id <- dimension_id
    sources$dimension <- item$label
    sources$dimension_order <- item$order
    sources$dimension_total <- population_total
    sources$proportion <- sources$count / population_total
    source_rows[[dimension_id]] <- sources[, c(
      "dimension_id", "dimension", "dimension_order", "comparison_source_category",
      "count", "dimension_total", "proportion"
    )]
  }

  source_data <- list(
    compound_comparison = compounds,
    coverage_summary = do.call(rbind, coverage_rows),
    coverage_metrics = do.call(rbind, coverage_metrics_rows),
    agreement_band_summary = do.call(rbind, agreement_rows),
    agreement_metrics = do.call(rbind, agreement_metrics_rows),
    score_pair_matrix = do.call(rbind, matrix_rows),
    comparison_status_counts = do.call(rbind, status_rows),
    comparison_source_counts = do.call(rbind, source_rows)
  )
  rownames(source_data$coverage_summary) <- NULL
  rownames(source_data$coverage_metrics) <- NULL
  rownames(source_data$agreement_band_summary) <- NULL
  rownames(source_data$agreement_metrics) <- NULL
  rownames(source_data$score_pair_matrix) <- NULL
  rownames(source_data$comparison_status_counts) <- NULL
  rownames(source_data$comparison_source_counts) <- NULL

  if (any(rowSums(matrix(
    source_data$coverage_summary$count,
    nrow = length(pbmt_dimension_schema), byrow = TRUE
  )) != population_total)) {
    stop("Coverage categories do not conserve the population.", call. = FALSE)
  }
  for (dimension_id in names(pbmt_dimension_schema)) {
    metric <- source_data$coverage_metrics[
      source_data$coverage_metrics$dimension_id == dimension_id, , drop = FALSE
    ]
    matrix_total <- sum(source_data$score_pair_matrix$count[
      source_data$score_pair_matrix$dimension_id == dimension_id
    ])
    agreement_total <- sum(source_data$agreement_band_summary$count[
      source_data$agreement_band_summary$dimension_id == dimension_id
    ])
    if (matrix_total != metric$shared_count || agreement_total != metric$shared_count) {
      stop("Shared-pair summaries do not conserve ", dimension_id, ".", call. = FALSE)
    }
  }
  list(
    source_data = source_data,
    statistics = list(
      population_total = population_total,
      excluded_rows = 0L,
      dimensions = lapply(
        seq_len(nrow(source_data$coverage_metrics)),
        function(index) as.list(source_data$coverage_metrics[index, , drop = FALSE])
      )
    )
  )
}

prepare_pbmt_dimension <- function(prepared, dimension_id) {
  list(
    source_data = lapply(
      prepared$source_data[c(
        "agreement_band_summary", "agreement_metrics", "score_pair_matrix",
        "comparison_status_counts"
      )],
      function(table) table[table$dimension_id == dimension_id, , drop = FALSE]
    ),
    statistics = as.list(prepared$source_data$agreement_metrics[
      prepared$source_data$agreement_metrics$dimension_id == dimension_id,
      , drop = FALSE
    ])
  )
}
