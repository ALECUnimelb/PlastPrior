plot_pbmt_combined_score_matrices <- function(source_data, config, variant) {
  matrix <- source_data$score_pair_matrix
  dimension_levels <- pbmt_dimension_levels
  panel_labels <- vapply(
    dimension_levels,
    function(dimension) {
      shared <- unique(matrix$shared_n[as.character(matrix$dimension) == dimension])
      if (length(shared) != 1L) {
        stop("Inconsistent shared n for ", dimension, ".", call. = FALSE)
      }
      paste0(dimension, "  (n = ", scales::comma(shared), ")")
    },
    character(1)
  )
  names(panel_labels) <- dimension_levels
  matrix$panel <- factor(
    panel_labels[as.character(matrix$dimension)], levels = panel_labels
  )
  matrix$plastchem_factor <- factor(
    pbmt_score_label(matrix$plastchem_score),
    levels = pbmt_score_label(pbmt_plastchem_score_levels)
  )
  matrix$computational_factor <- factor(
    pbmt_score_label(matrix$computational_score),
    levels = pbmt_score_label(pbmt_computational_score_levels)
  )
  matrix$count_label <- ifelse(matrix$count > 0, scales::comma(matrix$count), "")
  matrix$label_colour <- ifelse(matrix$fraction_of_shared >= 0.18, "white", "#222222")
  matrix$exact_cell <- as.logical(matrix$exact_cell)
  palette <- unlist(config$score_pair_palette, use.names = TRUE)
  ggplot2::ggplot(
    matrix,
    ggplot2::aes(x = plastchem_factor, y = computational_factor)
  ) +
    ggplot2::geom_tile(
      ggplot2::aes(fill = fraction_of_shared), colour = "white", linewidth = 0.45
    ) +
    ggplot2::geom_tile(
      data = matrix[matrix$exact_cell, , drop = FALSE],
      fill = NA, colour = "#111111", linewidth = 0.7
    ) +
    ggplot2::geom_text(
      ggplot2::aes(label = count_label, colour = label_colour),
      family = resolve_manuscript_font(), fontface = "bold",
      size = 2.25, show.legend = FALSE
    ) +
    ggplot2::facet_wrap(~panel, ncol = 2) +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_fill_gradient(
      low = palette[["low"]], high = palette[["high"]],
      limits = c(0, max(matrix$fraction_of_shared)),
      labels = scales::percent_format(accuracy = 1),
      oob = scales::squish,
      name = "Share of\nshared set"
    ) +
    ggplot2::scale_x_discrete(drop = FALSE) +
    ggplot2::scale_y_discrete(drop = FALSE) +
    ggplot2::coord_equal(expand = FALSE) +
    ggplot2::labs(
      title = "Complete PBMT score-pair distributions",
      subtitle = paste0(
        "Fill is normalized within each dimension's shared set; cell labels are true counts. ",
        "Outlined diagonal cells denote exact agreement."
      ),
      x = "PlastChem score", y = "Independent score"
    ) +
    pbmt_theme(base_size = 7) +
    ggplot2::theme(
      axis.line = ggplot2::element_blank(),
      axis.ticks = ggplot2::element_blank(),
      legend.position = "right",
      legend.key.height = grid::unit(15, "mm"),
      panel.spacing = grid::unit(5, "mm"),
      plot.margin = ggplot2::margin(5, 7, 5, 7)
    )
}
