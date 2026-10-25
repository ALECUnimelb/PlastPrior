nonempty_sql <- function(column) {
  paste0(
    "(", column, " IS NOT NULL AND TRIM(", column, ") <> '' ",
    "AND LOWER(TRIM(", column, ")) NOT IN ",
    "('nan','none','null','na','n/a','missing','unknown'))"
  )
}

as_boolean_flag <- function(values, column_name) {
  text <- tolower(trimws(as.character(values)))
  missing <- is.na(values) | !nzchar(text)
  output <- rep(NA, length(values))
  output[text %in% c("1", "1.0", "true", "yes", "y")] <- TRUE
  output[text %in% c("0", "0.0", "false", "no", "n")] <- FALSE
  if (any(missing) || any(is.na(output))) {
    stop(column_name, " contains missing or unsupported boolean values.", call. = FALSE)
  }
  output
}

stable_source_colors <- function(source_ids, config) {
  known <- unlist(config$source_palette, use.names = TRUE)
  fallback <- unlist(config$fallback_source_palette, use.names = FALSE)
  if (length(fallback) == 0L) {
    stop("figure.yml must define at least one fallback source color.", call. = FALSE)
  }
  colors <- vapply(source_ids, function(source_id) {
    if (source_id %in% names(known)) {
      return(unname(known[[source_id]]))
    }
    bytes <- utf8ToInt(source_id)
    index <- (sum(bytes * seq_along(bytes)) %% length(fallback)) + 1L
    fallback[[index]]
  }, character(1))
  names(colors) <- source_ids
  colors
}

stable_recovery_colors <- function(route_codes, config) {
  known <- unlist(config$recovery_palette, use.names = TRUE)
  fallback <- unlist(config$fallback_recovery_palette, use.names = FALSE)
  if (length(fallback) == 0L) {
    stop("figure.yml must define at least one fallback recovery color.", call. = FALSE)
  }
  colors <- vapply(route_codes, function(route_code) {
    if (route_code %in% names(known)) {
      return(unname(known[[route_code]]))
    }
    bytes <- utf8ToInt(route_code)
    index <- (sum(bytes * seq_along(bytes)) %% length(fallback)) + 1L
    fallback[[index]]
  }, character(1))
  names(colors) <- route_codes
  colors
}

recovery_color_group <- function(route_code) {
  dplyr::case_when(
    route_code == "reported_smile" ~ "recovery:reported",
    startsWith(route_code, "plastchem_") ~ "recovery:plastchem",
    startsWith(route_code, "pubchemlite_") ~ "recovery:pubchemlite",
    startsWith(route_code, "norman_") ~ "recovery:norman",
    route_code == "unresolved" ~ "invalid",
    TRUE ~ paste0("recovery:", route_code)
  )
}

read_source_catalog <- function(snapshot) {
  catalog <- read_snapshot_sql_query(
    snapshot$audit_path,
    paste(
      "SELECT source_id, display_label, formal_name, role, role_description,",
      "membership_column, membership_definition_version",
      "FROM source_catalog ORDER BY source_id"
    )
  )
  assert_columns(
    catalog,
    c(
      "source_id", "display_label", "formal_name", "role",
      "membership_column", "membership_definition_version"
    ),
    "source_catalog"
  )
  if (nrow(catalog) < 2L || anyDuplicated(catalog$source_id)) {
    stop("source_catalog must contain at least two unique analytical sources.", call. = FALSE)
  }
  if (any(!nzchar(trimws(catalog$display_label)))) {
    stop("source_catalog contains an empty display label.", call. = FALSE)
  }
  catalog
}

read_source_attrition <- function(snapshot) {
  attrition <- read_snapshot_sql_query(
    snapshot$audit_path,
    paste(
      "SELECT source_id, raw_row_count, harmonized_record_count,",
      "resolved_record_count, unresolved_record_count, unique_compound_count,",
      "collapsed_record_count, definition_version FROM source_attrition"
    )
  )
  numeric_columns <- c(
    "raw_row_count", "harmonized_record_count", "resolved_record_count",
    "unresolved_record_count", "unique_compound_count", "collapsed_record_count"
  )
  attrition[numeric_columns] <- lapply(attrition[numeric_columns], as.integer)
  attrition
}

record_flow_query <- function() {
  has_smiles <- nonempty_sql("sr.original_smiles")
  has_inchikey <- nonempty_sql("sr.original_inchikey")
  has_cas <- nonempty_sql("sr.cas")
  has_resolved <- nonempty_sql("ir.resolved_inchikey_std")
  paste0(
    "WITH record_flow AS (",
    " SELECT sr.source_id,",
    " CASE",
    " WHEN ", has_smiles, " THEN 'reported_smiles'",
    " WHEN ", has_inchikey, " THEN 'inchikey_only'",
    " WHEN ", has_cas, " THEN 'cas_only'",
    " ELSE 'no_identifier' END AS identifier_class,",
    " COALESCE(NULLIF(TRIM(ir.resolution_method), ''), 'unresolved') AS recovery_route,",
    " CASE WHEN ", has_resolved,
    " THEN 'resolved_records' ELSE 'unresolved_records' END AS resolution_state",
    " FROM source_records sr JOIN identity_resolution ir",
    " ON ir.source_record_id = sr.source_record_id",
    ")",
    " SELECT source_id, identifier_class, recovery_route, resolution_state,",
    " COUNT(*) AS record_count FROM record_flow",
    " GROUP BY source_id, identifier_class, recovery_route, resolution_state",
    " ORDER BY source_id, identifier_class, recovery_route, resolution_state"
  )
}

recovery_display_label <- function(route) {
  approved <- c(
    reported_smile = "Reported SMILES",
    pubchemlite_inchikey = "PubChemLite InChIKey",
    plastchem_inchikey = "PlastChem InChIKey",
    norman_inchikey = "NORMAN InChIKey",
    plastchem_cas = "PlastChem CAS",
    norman_cas = "NORMAN CAS",
    unresolved = "Unresolved"
  )
  ifelse(
    route %in% names(approved),
    unname(approved[route]),
    stringr::str_to_title(gsub("_", " ", route, fixed = TRUE))
  )
}

primary_qc_reason <- function(value) {
  priority <- c("multi_component", "contains_metal", "mw_out_of_range", "non_organic")
  if (is.na(value) || !nzchar(trimws(as.character(value)))) {
    return("other")
  }
  flags <- trimws(strsplit(as.character(value), ";", fixed = TRUE)[[1]])
  observed <- priority[priority %in% flags]
  if (length(observed) == 0L) "other" else observed[[1]]
}

collapse_flow_edges <- function(data, source_column, target_column, stage, unit, notes) {
  data |>
    dplyr::group_by(.data[[source_column]], .data[[target_column]]) |>
    dplyr::summarise(value = sum(.data$record_count), .groups = "drop") |>
    dplyr::rename(source_id = 1L, target_id = 2L) |>
    dplyr::mutate(stage = stage, unit = unit, notes = notes)
}

assign_sankey_node_order <- function(nodes) {
  nodes |>
    dplyr::arrange(
      .data$layer,
      .data$order_hint,
      dplyr::desc(.data$node_value),
      .data$node_id
    ) |>
    dplyr::group_by(.data$layer) |>
    dplyr::mutate(node_order = dplyr::row_number()) |>
    dplyr::ungroup()
}

prepare_sankey_source_data <- function(snapshot, compounds, catalog, attrition, config) {
  aggregate <- read_snapshot_sql_query(snapshot$audit_path, record_flow_query()) |>
    dplyr::mutate(record_count = as.integer(.data$record_count))
  if (nrow(aggregate) == 0L) {
    stop("The snapshot contains no record-level identity flow.", call. = FALSE)
  }
  unknown_sources <- setdiff(unique(aggregate$source_id), catalog$source_id)
  if (length(unknown_sources) > 0L) {
    stop(
      "Record flow contains source(s) absent from source_catalog: ",
      paste(unknown_sources, collapse = ", "),
      call. = FALSE
    )
  }

  aggregate <- aggregate |>
    dplyr::mutate(
      source_node = paste0("source:", .data$source_id),
      identifier_node = paste0("identifier:", .data$identifier_class),
      recovery_node = paste0("recovery:", .data$recovery_route),
      resolution_node = paste0("resolution:", .data$resolution_state)
    )

  edges <- dplyr::bind_rows(
    collapse_flow_edges(
      aggregate,
      "source_node",
      "identifier_node",
      "source_to_identifier",
      "records",
      "Source records classified by the strongest reported identifier."
    ),
    collapse_flow_edges(
      aggregate,
      "identifier_node",
      "recovery_node",
      "identifier_to_recovery",
      "records",
      "Reported identifier class mapped to the structure-recovery route."
    ),
    collapse_flow_edges(
      aggregate,
      "recovery_node",
      "resolution_node",
      "recovery_to_resolution",
      "records",
      "Recovery route mapped to record-level standardized-InChIKey resolution."
    )
  )

  total_records <- sum(aggregate$record_count)
  resolved_records <- sum(aggregate$record_count[aggregate$resolution_state == "resolved_records"])
  unresolved_records <- total_records - resolved_records
  unique_compounds <- nrow(compounds)
  collapsed_records <- resolved_records - unique_compounds
  if (collapsed_records < 0L) {
    stop("Resolved record count is smaller than the unique-compound count.", call. = FALSE)
  }

  edges <- dplyr::bind_rows(
    edges,
    tibble::tibble(
      source_id = "resolution:resolved_records",
      target_id = c("dedup:unique_compounds", "dedup:collapsed_records"),
      value = c(unique_compounds, collapsed_records),
      stage = "resolution_to_deduplication",
      unit = c("unique compounds", "records"),
      notes = c(
        "Unique full standardized-InChIKey compounds retained after deduplication.",
        "Additional resolved source records collapsed as duplicates."
      )
    )
  )

  keep_for_vega <- as_boolean_flag(compounds$keep_for_vega, "keep_for_vega")
  qsar_status <- rep("eligible", nrow(compounds))
  qsar_status[!keep_for_vega] <- vapply(
    compounds$qc_flags[!keep_for_vega],
    primary_qc_reason,
    character(1)
  )
  qsar_counts <- tibble::tibble(qsar_status = qsar_status) |>
    dplyr::count(.data$qsar_status, name = "value") |>
    dplyr::mutate(
      source_id = "dedup:unique_compounds",
      target_id = paste0("qsar:", .data$qsar_status),
      stage = "unique_compounds_to_qsar",
      unit = "unique compounds",
      notes = "Compound-level QSAR eligibility using one declared primary exclusion reason."
    ) |>
    dplyr::select(
      source_id, target_id, value, stage, unit, notes
    )
  edges <- dplyr::bind_rows(edges, qsar_counts)

  source_colors <- stable_source_colors(catalog$source_id, config)
  source_meta <- catalog |>
    dplyr::transmute(
      node_id = paste0("source:", .data$source_id),
      display_label = .data$display_label,
      layer = 1L,
      order_hint = 0L,
      order_policy = "size_desc",
      node_color = unname(source_colors[.data$source_id]),
      color_group = paste0("source:", .data$source_id)
    )
  identifier_labels <- c(
    reported_smiles = "Reported SMILES",
    inchikey_only = "InChIKey only",
    cas_only = "CAS only",
    no_identifier = "No reported identifier"
  )
  identifier_meta <- tibble::tibble(
    code = names(identifier_labels),
    display_label = unname(identifier_labels),
    layer = 2L,
    order_hint = 0L,
    order_policy = "size_desc",
    node_color = c("#4E7896", "#6C9A91", "#B59A58", "#B8BEC4"),
    color_group = "identifier"
  ) |>
    dplyr::mutate(node_id = paste0("identifier:", .data$code)) |>
    dplyr::select(
      node_id, display_label, layer, order_hint, order_policy,
      node_color, color_group
    )
  recovery_codes <- unique(aggregate$recovery_route)
  recovery_colors <- stable_recovery_colors(recovery_codes, config)
  recovery_meta <- tibble::tibble(code = recovery_codes) |>
    dplyr::mutate(
      display_label = recovery_display_label(.data$code),
      layer = 3L,
      order_hint = 0L,
      order_policy = "size_desc",
      node_color = unname(recovery_colors[.data$code]),
      color_group = recovery_color_group(.data$code),
      node_id = paste0("recovery:", .data$code)
    ) |>
    dplyr::select(
      node_id, display_label, layer, order_hint, order_policy,
      node_color, color_group
    )
  resolution_meta <- tibble::tibble(
    node_id = c("resolution:resolved_records", "resolution:unresolved_records"),
    display_label = c("Resolved records", "Unresolved records"),
    layer = 4L,
    order_hint = 1:2,
    order_policy = "semantic",
    node_color = c("#2F74B5", "#B8BEC4"),
    color_group = c("resolved", "invalid")
  )
  dedup_meta <- tibble::tibble(
    node_id = c("dedup:unique_compounds", "dedup:collapsed_records"),
    display_label = c("Unique compounds retained", "Duplicate records collapsed"),
    layer = 5L,
    order_hint = 1:2,
    order_policy = "semantic",
    node_color = c("#357FBC", "#B7A4B9"),
    color_group = c("resolved", "dedup")
  )
  qsar_labels <- c(
    eligible = "QSAR eligible",
    multi_component = "Multi-component",
    contains_metal = "Contains metal",
    mw_out_of_range = "MW outside range",
    non_organic = "Non-organic",
    other = "Other exclusion"
  )
  qsar_codes <- sub("^qsar:", "", qsar_counts$target_id)
  qsar_meta <- tibble::tibble(code = qsar_codes) |>
    dplyr::mutate(
      node_id = paste0("qsar:", .data$code),
      display_label = ifelse(
        .data$code %in% names(qsar_labels),
        unname(qsar_labels[.data$code]),
        stringr::str_to_title(gsub("_", " ", .data$code, fixed = TRUE))
      ),
      layer = 6L,
      order_hint = ifelse(.data$code == "eligible", 1L, 2L),
      order_policy = "eligible_then_size_desc",
      node_color = ifelse(.data$code == "eligible", "#2B83BA", "#AEB5BB"),
      color_group = ifelse(.data$code == "eligible", "eligible", "invalid")
    ) |>
    dplyr::select(
      node_id, display_label, layer, order_hint, order_policy,
      node_color, color_group
    )

  nodes <- dplyr::bind_rows(
    source_meta, identifier_meta, recovery_meta,
    resolution_meta, dedup_meta, qsar_meta
  ) |>
    dplyr::filter(.data$node_id %in% unique(c(edges$source_id, edges$target_id)))
  incoming <- edges |>
    dplyr::group_by(node_id = .data$target_id) |>
    dplyr::summarise(incoming = sum(.data$value), .groups = "drop")
  outgoing <- edges |>
    dplyr::group_by(node_id = .data$source_id) |>
    dplyr::summarise(outgoing = sum(.data$value), .groups = "drop")
  nodes <- nodes |>
    dplyr::left_join(incoming, by = "node_id") |>
    dplyr::left_join(outgoing, by = "node_id") |>
    dplyr::mutate(
      incoming = dplyr::coalesce(.data$incoming, 0),
      outgoing = dplyr::coalesce(.data$outgoing, 0),
      node_value = pmax(.data$incoming, .data$outgoing)
    ) |>
    assign_sankey_node_order()

  source_counts <- aggregate |>
    dplyr::group_by(source_id = .data$source_id) |>
    dplyr::summarise(record_count = sum(.data$record_count), .groups = "drop")
  source_validation <- catalog |>
    dplyr::select(source_id) |>
    dplyr::left_join(source_counts, by = "source_id") |>
    dplyr::left_join(
      attrition |>
        dplyr::select(source_id, harmonized_record_count),
      by = "source_id"
    ) |>
    dplyr::mutate(matches = .data$record_count == .data$harmonized_record_count)
  if (any(!source_validation$matches)) {
    stop("Record-flow counts disagree with source_attrition.", call. = FALSE)
  }
  if (sum(attrition$resolved_record_count) != resolved_records ||
      sum(attrition$unresolved_record_count) != unresolved_records) {
    stop("Resolution totals disagree with source_attrition.", call. = FALSE)
  }
  stage_totals <- edges |>
    dplyr::group_by(.data$stage) |>
    dplyr::summarise(value = sum(.data$value), .groups = "drop")
  expected_stage_totals <- c(
    source_to_identifier = total_records,
    identifier_to_recovery = total_records,
    recovery_to_resolution = total_records,
    resolution_to_deduplication = resolved_records,
    unique_compounds_to_qsar = unique_compounds
  )
  observed_stage_totals <- stats::setNames(stage_totals$value, stage_totals$stage)
  if (!identical(
    as.integer(observed_stage_totals[names(expected_stage_totals)]),
    as.integer(expected_stage_totals)
  )) {
    stop("One or more Sankey stages fail flow-conservation checks.", call. = FALSE)
  }

  summary <- tibble::tibble(
    metric = c(
      "source_records", "resolved_records", "unresolved_records",
      "unique_compounds", "collapsed_duplicate_records",
      "qsar_eligible_compounds", "qsar_ineligible_compounds"
    ),
    value = c(
      total_records, resolved_records, unresolved_records,
      unique_compounds, collapsed_records,
      sum(keep_for_vega), sum(!keep_for_vega)
    ),
    unit = c(rep("records", 3), rep("unique compounds", 1), "records", rep("unique compounds", 2))
  )

  list(
    aggregate = aggregate |>
      dplyr::select(
        source_id, identifier_class, recovery_route, resolution_state, record_count
      ),
    edges = edges,
    nodes = nodes,
    summary = summary,
    source_validation = source_validation
  )
}

prepare_database_overlap <- function(snapshot, compounds, catalog, attrition, config) {
  memberships <- read_snapshot_sql_query(
    snapshot$audit_path,
    paste(
      "SELECT inchikey_std, source_id, member, definition_version",
      "FROM source_membership WHERE member = 1",
      "ORDER BY inchikey_std, source_id"
    )
  )
  assert_columns(
    memberships,
    c("inchikey_std", "source_id", "member", "definition_version"),
    "source_membership"
  )
  unknown_sources <- setdiff(unique(memberships$source_id), catalog$source_id)
  if (length(unknown_sources) > 0L) {
    stop(
      "source_membership contains source(s) absent from source_catalog: ",
      paste(unknown_sources, collapse = ", "),
      call. = FALSE
    )
  }
  compound_keys <- toupper(trimws(compounds$Inchikey_std))
  if (anyDuplicated(compound_keys) || any(!nzchar(compound_keys))) {
    stop("Compound CSV keys are missing or duplicated.", call. = FALSE)
  }
  membership_keys <- toupper(trimws(memberships$inchikey_std))
  if (any(!membership_keys %in% compound_keys)) {
    stop("source_membership contains keys absent from the compound CSV.", call. = FALSE)
  }

  source_sizes <- memberships |>
    dplyr::count(.data$source_id, name = "set_size")
  set_sizes <- catalog |>
    dplyr::select(
      source_id, display_label, formal_name,
      membership_column, membership_definition_version
    ) |>
    dplyr::left_join(source_sizes, by = "source_id") |>
    dplyr::mutate(set_size = dplyr::coalesce(as.integer(.data$set_size), 0L)) |>
    dplyr::left_join(
      attrition |>
        dplyr::select(source_id, attrition_unique_compounds = unique_compound_count),
      by = "source_id"
    )
  if (any(set_sizes$set_size != set_sizes$attrition_unique_compounds)) {
    stop("source_membership set sizes disagree with source_attrition.", call. = FALSE)
  }
  colors <- stable_source_colors(set_sizes$source_id, config)
  set_sizes <- set_sizes |>
    dplyr::mutate(
      color = unname(colors[.data$source_id]),
      compact_column = paste0("source_member_", .data$source_id)
    ) |>
    dplyr::arrange(dplyr::desc(.data$set_size), .data$source_id) |>
    dplyr::mutate(row_order = dplyr::row_number())
  source_ids <- set_sizes$source_id

  matrix_values <- matrix(
    0L,
    nrow = length(compound_keys),
    ncol = length(source_ids),
    dimnames = list(compound_keys, source_ids)
  )
  row_index <- match(membership_keys, compound_keys)
  column_index <- match(memberships$source_id, source_ids)
  matrix_values[cbind(row_index, column_index)] <- 1L
  if (any(rowSums(matrix_values) == 0L)) {
    stop("Every compound must belong to at least one registered source database.", call. = FALSE)
  }

  compact_columns <- paste0("source_member_", source_ids)
  assert_columns(compounds, compact_columns, "ChemicalPrio_compounds.csv")
  compact_matrix <- vapply(compact_columns, function(column) {
    as.integer(as_boolean_flag(compounds[[column]], column))
  }, integer(nrow(compounds)))
  compact_matrix <- compact_matrix[, compact_columns, drop = FALSE]
  colnames(compact_matrix) <- source_ids
  if (!identical(unname(matrix_values), unname(compact_matrix))) {
    mismatches <- sum(matrix_values != compact_matrix)
    stop(
      "CSV source_member_* fields disagree with SQLite source_membership at ",
      mismatches, " cell(s).",
      call. = FALSE
    )
  }

  patterns <- apply(matrix_values, 1L, function(row) {
    paste(source_ids[row == 1L], collapse = "|")
  })
  membership_table <- tibble::as_tibble(matrix_values) |>
    dplyr::mutate(
      Inchikey_std = compounds$Inchikey_std,
      database_pattern = patterns,
      database_count = rowSums(matrix_values),
      .before = 1L
    )
  names(membership_table)[match(source_ids, names(membership_table))] <- compact_columns

  intersections <- membership_table |>
    dplyr::count(.data$database_pattern, .data$database_count, name = "compound_count") |>
    dplyr::arrange(
      dplyr::desc(.data$compound_count),
      dplyr::desc(.data$database_count),
      .data$database_pattern
    ) |>
    dplyr::mutate(intersection_rank = dplyr::row_number(), .before = 1L)
  for (source_id in source_ids) {
    column <- paste0("source_member_", source_id)
    intersections[[column]] <- as.integer(vapply(
      strsplit(intersections$database_pattern, "|", fixed = TRUE),
      function(active) source_id %in% active,
      logical(1)
    ))
  }
  if (sum(intersections$compound_count) != nrow(compounds)) {
    stop("Exact database intersections do not conserve the compound population.", call. = FALSE)
  }

  comparison <- tolower(config$upset$comparison)
  threshold <- as.integer(config$upset$min_intersection_size)
  if (!(comparison %in% c("gt", "gte")) || is.na(threshold) || threshold < 1L) {
    stop("UpSet comparison must be gt/gte and threshold must be positive.", call. = FALSE)
  }
  eligible <- if (comparison == "gte") {
    intersections$compound_count >= threshold
  } else {
    intersections$compound_count > threshold
  }
  selected <- intersections[eligible, , drop = FALSE]
  maximum <- config$upset$max_intersections
  if (!is.null(maximum)) {
    maximum <- as.integer(maximum)
    if (is.na(maximum) || maximum < 1L) {
      stop("UpSet max_intersections must be null or a positive integer.", call. = FALSE)
    }
    selected <- utils::head(selected, maximum)
  }
  if (nrow(selected) == 0L) {
    stop("No exact database intersections remain after applying the configured filter.", call. = FALSE)
  }
  selected <- selected |>
    dplyr::mutate(display_rank = dplyr::row_number(), .before = 1L)
  displayed_compounds <- sum(selected$compound_count)
  coverage <- 100 * displayed_compounds / nrow(compounds)
  selection_summary <- tibble::tibble(
    metric = c(
      "unique_compounds", "registered_databases", "nonempty_exact_intersections",
      "minimum_intersection_size", "comparison", "maximum_intersections",
      "displayed_intersections", "displayed_compounds", "displayed_coverage_percent",
      "excluded_intersections", "excluded_compounds"
    ),
    value = as.character(c(
      nrow(compounds), nrow(set_sizes), nrow(intersections),
      threshold, comparison, if (is.null(maximum)) "all" else maximum,
      nrow(selected), displayed_compounds, round(coverage, 3),
      nrow(intersections) - nrow(selected), nrow(compounds) - displayed_compounds
    ))
  )

  list(
    membership = membership_table,
    set_sizes = set_sizes,
    intersections = intersections,
    selected = selected,
    summary = selection_summary,
    source_ids = source_ids,
    compact_columns = compact_columns,
    displayed_compounds = displayed_compounds,
    displayed_coverage = coverage,
    comparison = comparison,
    threshold = threshold,
    maximum = maximum
  )
}
