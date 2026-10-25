# Independent panel tables; reuse prepared statistics rather than rescore compounds.
prepare_priority_exports <- function(prepared, config, variant = "publication") {
  if (!variant %in% c("publication", "audit_all_values")) stop("Unknown variant.")
  audit <- identical(variant, "audit_all_values")
  get_table <- function(panel, table) prepared[[panel]]$source_data[[table]]
  palette <- function(name, categories) {
    colors <- unlist(config[[name]], use.names = TRUE)[as.character(categories)]
    if (anyNA(colors)) stop("Export category missing from palette: ", name)
    unname(colors)
  }
  population <- function(table, panel) {
    stats <- prepared[[panel]]$statistics
    table$population_full <- stats$population_full
    table$population_plotted <- if (is.null(stats$population_plotted)) {
      stats$population_full
    } else stats$population_plotted
    table$population_excluded <- table$population_full - table$population_plotted
    table
  }
  bins <- function(table) {
    table$bin_lower_inclusive <- table$score_bin
    table$bin_upper_exclusive <- table$score_bin + 1
    table
  }
  check_total <- function(table) {
    if (sum(table$compound_count) != unique(table$population_plotted)) {
      stop("Export population does not match plotted data.")
    }
  }
  a <- population(bins(get_table("priority_score_distribution", "priority_distribution")),
                  "priority_score_distribution")
  a$priority_order <- match(a$Priority_tier, names(config$priority_palette))
  a$color <- palette("priority_palette", a$Priority_tier)
  a$score_bin_total <- ave(a$compound_count, a$score_bin, FUN = sum)
  a$label_count <- a$score_bin_total
  a$label_eligible <- as.integer(!duplicated(a$score_bin) & a$score_bin_total >= if (audit) 1 else max(
    config$display$priority_distribution_label_min_count,
    sum(a$compound_count) * config$display$priority_distribution_label_min_fraction))
  check_total(a)

  inset <- population(get_table("regulatory_context_inset", "priority_regulatory_cross"),
                      "regulatory_context_inset")
  inset$priority_color <- palette("priority_palette", inset$priority_tier)
  inset$regulatory_color <- palette("regulatory_palette", inset$regulatory_status)
  inset$proportion_of_population <- inset$compound_count / inset$population_full
  inset$label_eligible <- as.integer(inset$compound_count > 0)
  inset_threshold <- if (audit) 0 else config$display$regulatory_internal_label_min_fraction
  inset$label_position <- ifelse(inset$compound_count == 0, "none",
    ifelse(inset$proportion_of_population >= inset_threshold, "inside", "outside"))
  if (!audit && !isTRUE(config$display$regulatory_show_small_callouts)) {
    inset$label_position[inset$label_position == "outside"] <- "none"
    inset$label_eligible <- as.integer(inset$label_position != "none")
  }
  inset$regulatory_context_is_score_input <- FALSE
  check_total(inset)

  b <- population(get_table("hazard_exposure_landscape", "hazard_exposure_pairs"),
                  "hazard_exposure_landscape")
  b$priority_order <- match(b$Priority_tier, names(config$priority_palette))
  b$color <- palette("priority_palette", b$Priority_tier)
  b$label_eligible <- as.integer(audit & b$compound_count >= config$display$hazard_exposure_label_min_count)
  b$hazard_axis_max <- config$thresholds$hazard_theoretical_max
  b$exposure_axis_max <- config$thresholds$exposure_theoretical_max
  b$low_priority_upper <- config$thresholds$low_priority_upper
  b$high_priority_lower <- config$thresholds$high_priority_lower
  b$moderate_component_min <- config$thresholds$moderate_component_min
  b$high_component_min <- config$thresholds$high_component_min
  b$priority_tier_policy_version <- config$priority_tier_policy_version
  check_total(b)

  c <- population(bins(get_table("score_decomposition", "score_decomposition_wide")),
                  "score_decomposition")
  if (any(abs(c$mean_hazard + c$mean_exposure - c$mean_priority_score) > 1e-8)) {
    stop("Exported mean components do not reconstruct the mean priority score.")
  }
  threshold <- if (audit) 0 else config$display$score_decomposition_label_min_contribution
  for (component in c("hazard", "exposure")) {
    c[[paste0(component, "_label_eligible")]] <- as.integer(c[[paste0("mean_", component)]] >= threshold)
    c[[paste0(component, "_color")]] <- palette("score_component_palette",
                                               if (component == "hazard") "Hazard" else "Exposure")
  }
  check_total(c)

  profile <- function(panel, color_key, threshold_key) {
    table <- population(get_table(panel, panel), panel)
    for (component in unique(table$component)) {
      rows <- table[table$component == component, , drop = FALSE]
      check_total(rows)
    }
    if (any(abs(table$proportion - table$compound_count / table$population_full) > 1e-10)) {
      stop("Exported profile proportions disagree with counts.")
    }
    table$color <- palette(color_key, table$score_class)
    threshold <- if (audit) config$display$audit_profile_label_min_fraction else config$display[[threshold_key]]
    table$label_eligible <- as.integer(table$proportion >= threshold & table$compound_count > 0)
    table$label_position <- ifelse(table$label_eligible == 1L, "inside", "none")
    table
  }
  d <- profile("hazard_component_profiles", "hazard_profile_palette", "hazard_profile_label_min_fraction")
  e <- profile("exposure_component_profiles", "exposure_profile_palette", "exposure_profile_label_min_fraction")
  joint <- e$component == "Food-contact + biomonitoring" & e$score_class == "High (2)" & e$compound_count > 0
  e$label_eligible[joint] <- 1L
  e$label_position[joint] <- "outside"
  list(figure3a_priority_distribution = a, figure3a_regulatory_inset = inset,
       figure3b_hazard_exposure = b, figure3c_score_decomposition = c,
       figure3d_hazard_profiles = d, figure3e_exposure_profiles = e)
}

write_priority_exports <- function(tables, export_dir) {
  dir.create(export_dir, recursive = TRUE, showWarnings = FALSE)
  for (name in names(tables)) {
    readr::write_excel_csv(tables[[name]], file.path(export_dir, paste0(name, ".csv")), na = "")
  }
}
