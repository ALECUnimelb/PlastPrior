plot_source_database_intersections <- function(overlap, config) {
  selected <- overlap$selected
  set_sizes <- overlap$set_sizes
  source_ids <- overlap$source_ids
  compact_columns <- overlap$compact_columns
  font_family <- resolve_manuscript_font()
  set_size_column_weight <- as.numeric(config$upset$set_size_column_weight)
  matrix_column_weight <- as.numeric(config$upset$matrix_column_weight)
  set_size_label_x <- as.numeric(config$upset$set_size_label_x)
  set_size_bar_xmin <- as.numeric(config$upset$set_size_bar_xmin)
  set_size_bar_max_width <- as.numeric(config$upset$set_size_bar_max_width)
  set_size_count_x <- as.numeric(config$upset$set_size_count_x)
  set_size_xlim_max <- as.numeric(config$upset$set_size_xlim_max)
  set_size_matrix_gap_mm <- as.numeric(config$upset$set_size_matrix_gap_mm)
  layout_values <- c(
    set_size_column_weight,
    matrix_column_weight,
    set_size_label_x,
    set_size_bar_xmin,
    set_size_bar_max_width,
    set_size_count_x,
    set_size_xlim_max,
    set_size_matrix_gap_mm
  )
  if (any(!is.finite(layout_values)) || any(layout_values <= 0) ||
      set_size_label_x >= set_size_bar_xmin ||
      set_size_bar_xmin + set_size_bar_max_width >= set_size_count_x ||
      set_size_count_x >= set_size_xlim_max) {
    stop("Configured UpSet set-size layout dimensions are invalid.", call. = FALSE)
  }

  matrix_data <- selected |>
    dplyr::select(display_rank, compound_count, dplyr::all_of(compact_columns)) |>
    tidyr::pivot_longer(
      cols = dplyr::all_of(compact_columns),
      names_to = "compact_column",
      values_to = "active"
    ) |>
    dplyr::left_join(
      set_sizes |>
        dplyr::select(
          source_id, display_label, compact_column, color, row_order
        ),
      by = "compact_column"
    ) |>
    dplyr::mutate(
      active = as.logical(.data$active),
      y = nrow(set_sizes) - .data$row_order + 1L,
      point_fill = dplyr::if_else(.data$active, .data$color, "#E8EDF2")
    )
  if (any(is.na(matrix_data$source_id))) {
    stop("UpSet membership columns failed to join source_catalog metadata.", call. = FALSE)
  }

  connector_data <- matrix_data |>
    dplyr::filter(.data$active) |>
    dplyr::group_by(.data$display_rank) |>
    dplyr::summarise(
      ymin = min(.data$y),
      ymax = max(.data$y),
      active_count = dplyr::n(),
      .groups = "drop"
    ) |>
    dplyr::filter(.data$active_count > 1L)
  row_bands <- set_sizes |>
    dplyr::transmute(
      y = nrow(set_sizes) - .data$row_order + 1L,
      fill = dplyr::if_else(.data$row_order %% 2L == 1L, "#F7F9FB", "#FFFFFF")
    )
  set_sizes_plot_data <- set_sizes |>
    dplyr::mutate(
      y = nrow(set_sizes) - .data$row_order + 1L,
      bar_width = set_size_bar_max_width * .data$set_size / max(.data$set_size)
    )

  intersection_count <- nrow(selected)
  matrix_point_size <- if (intersection_count > 50L) 1.55 else 2.15
  inactive_point_size <- if (intersection_count > 50L) 0.72 else 0.95
  top_label_angle <- if (intersection_count > 18L) 90 else 0
  top_label_hjust <- if (top_label_angle == 90) 0 else 0.5
  comparator_label <- if (overlap$comparison == "gte") "≥" else ">"
  unique_compounds <- as.integer(
    overlap$summary$value[overlap$summary$metric == "unique_compounds"]
  )
  coverage_note <- paste0(
    "Exact intersections ", comparator_label, overlap$threshold,
    "; ", scales::comma(overlap$displayed_compounds), " of ",
    scales::comma(unique_compounds),
    " compounds shown (", scales::number(overlap$displayed_coverage, accuracy = 0.1), "%)."
  )

  intersection_bar <- ggplot2::ggplot(
    selected,
    ggplot2::aes(x = .data$display_rank, y = .data$compound_count)
  ) +
    ggplot2::geom_col(fill = "#26394C", width = 0.72) +
    ggplot2::geom_text(
      ggplot2::aes(label = scales::comma(.data$compound_count)),
      angle = top_label_angle,
      hjust = top_label_hjust,
      vjust = if (top_label_angle == 90) 0.45 else -0.3,
      size = 5.3 / ggplot2::.pt,
      family = font_family,
      fontface = "bold",
      colour = "#1D2733"
    ) +
    ggplot2::scale_x_continuous(
      limits = c(0.35, intersection_count + 0.65),
      breaks = NULL,
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::scale_y_continuous(
      labels = scales::comma,
      expand = ggplot2::expansion(mult = c(0, if (top_label_angle == 90) 0.30 else 0.18))
    ) +
    ggplot2::labs(x = NULL, y = "Intersection size") +
    theme_manuscript(base_size = 6.5, base_family = font_family) +
    ggplot2::theme(
      axis.line.x = ggplot2::element_blank(),
      axis.ticks.x = ggplot2::element_blank(),
      axis.text.x = ggplot2::element_blank(),
      axis.title.y = ggplot2::element_text(face = "bold", size = 6.1),
      axis.text.y = ggplot2::element_text(size = 5.5),
      plot.margin = ggplot2::margin(3, 2, 0, 0, unit = "mm")
    )

  set_size_plot <- ggplot2::ggplot(set_sizes_plot_data, ggplot2::aes(y = .data$y)) +
    ggplot2::geom_text(
      ggplot2::aes(x = set_size_label_x, label = .data$display_label),
      hjust = 1,
      family = font_family,
      size = 5.7 / ggplot2::.pt,
      fontface = "bold",
      colour = "#111820"
    ) +
    ggplot2::geom_rect(
      ggplot2::aes(
        xmin = set_size_bar_xmin,
        xmax = set_size_bar_xmin + .data$bar_width,
        ymin = .data$y - 0.27,
        ymax = .data$y + 0.27,
        fill = .data$color
      ),
      colour = NA
    ) +
    ggplot2::geom_text(
      ggplot2::aes(x = set_size_count_x, label = scales::comma(.data$set_size)),
      hjust = 0,
      family = font_family,
      size = 5.4 / ggplot2::.pt,
      colour = "#66727E",
      fontface = "bold"
    ) +
    ggplot2::annotate(
      "text",
      x = set_size_label_x,
      y = nrow(set_sizes) + 1.0,
      label = "COMPOUND COUNT",
      hjust = 1,
      family = font_family,
      size = 5.5 / ggplot2::.pt,
      fontface = "bold",
      colour = "#66727E"
    ) +
    ggplot2::scale_fill_identity() +
    ggplot2::coord_cartesian(
      xlim = c(0, set_size_xlim_max),
      ylim = c(0.4, nrow(set_sizes) + 1.3),
      clip = "off"
    ) +
    ggplot2::theme_void(base_family = font_family) +
    ggplot2::theme(
      plot.margin = ggplot2::margin(
        0,
        set_size_matrix_gap_mm,
        4,
        0,
        unit = "mm"
      )
    )

  matrix_plot <- ggplot2::ggplot(matrix_data, ggplot2::aes(x = .data$display_rank, y = .data$y)) +
    ggplot2::geom_rect(
      data = row_bands,
      ggplot2::aes(
        xmin = 0.35,
        xmax = intersection_count + 0.65,
        ymin = .data$y - 0.43,
        ymax = .data$y + 0.43,
        fill = .data$fill
      ),
      inherit.aes = FALSE,
      colour = NA
    ) +
    ggplot2::geom_segment(
      data = connector_data,
      ggplot2::aes(
        x = .data$display_rank,
        xend = .data$display_rank,
        y = .data$ymin,
        yend = .data$ymax
      ),
      inherit.aes = FALSE,
      colour = "#26394C",
      linewidth = 0.38
    ) +
    ggplot2::geom_point(
      data = matrix_data |> dplyr::filter(!.data$active),
      size = inactive_point_size,
      shape = 21,
      fill = "#E8EDF2",
      colour = "#D0D9E0",
      stroke = 0.18
    ) +
    ggplot2::geom_point(
      data = matrix_data |> dplyr::filter(.data$active),
      ggplot2::aes(colour = .data$point_fill),
      size = matrix_point_size,
      shape = 16
    ) +
    ggplot2::scale_fill_identity() +
    ggplot2::scale_colour_identity() +
    ggplot2::scale_x_continuous(
      limits = c(0.35, intersection_count + 0.65),
      breaks = NULL,
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::scale_y_continuous(
      limits = c(0.4, nrow(set_sizes) + 0.6),
      breaks = NULL,
      expand = ggplot2::expansion(mult = c(0, 0))
    ) +
    ggplot2::labs(x = NULL, y = NULL) +
    ggplot2::theme_void(base_family = font_family) +
    ggplot2::theme(
      plot.margin = ggplot2::margin(0, 2, 4, set_size_matrix_gap_mm, unit = "mm")
    )

  top_left <- patchwork::plot_spacer()
  top_row <- top_left + intersection_bar +
    patchwork::plot_layout(
      widths = c(set_size_column_weight, matrix_column_weight)
    )
  bottom_row <- set_size_plot + matrix_plot +
    patchwork::plot_layout(
      widths = c(set_size_column_weight, matrix_column_weight)
    )
  panel <- top_row / bottom_row +
    patchwork::plot_layout(
      heights = c(0.45, 0.55)
    ) +
    patchwork::plot_annotation(
      caption = coverage_note,
      theme = ggplot2::theme(
        plot.caption = ggplot2::element_text(
          family = font_family,
          size = 5.6,
          colour = "#5B6673",
          hjust = 1,
          margin = ggplot2::margin(t = 1.5, unit = "mm")
        ),
        plot.margin = ggplot2::margin(0, 1, 0, 1, unit = "mm")
      )
    )

  list(
    plot = panel,
    matrix_data = matrix_data,
    connector_data = connector_data,
    coverage_note = coverage_note
  )
}
