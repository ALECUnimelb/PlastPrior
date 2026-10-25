prepare_pbmt_coverage <- function(prepared) {
  list(
    source_data = prepared$source_data[c("coverage_summary", "coverage_metrics")],
    statistics = list(
      population_total = unique(prepared$source_data$coverage_metrics$population_total),
      dimensions = lapply(
        seq_len(nrow(prepared$source_data$coverage_metrics)),
        function(index) as.list(
          prepared$source_data$coverage_metrics[index, , drop = FALSE]
        )
      )
    )
  )
}

