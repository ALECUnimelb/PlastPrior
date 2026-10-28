bezier_value <- function(p0, p1, p2, p3, t) {
  ((1 - t)^3 * p0) + (3 * (1 - t)^2 * t * p1) +
    (3 * (1 - t) * t^2 * p2) + (t^3 * p3)
}

pack_label_centres <- function(desired, heights, gap, lower = 0.015, upper = 0.985) {
  if (length(desired) == 0L) {
    return(numeric())
  }
  order_index <- order(desired)
  desired_ordered <- desired[order_index]
  heights_ordered <- heights[order_index]
  required <- sum(heights_ordered) + gap * max(length(desired) - 1L, 0L)
  if (required > upper - lower) {
    stop(
      "Sankey labels require more vertical space than the configured panel provides.",
      call. = FALSE
    )
  }

  positioned <- numeric(length(desired_ordered))
  positioned[[1]] <- max(desired_ordered[[1]], lower + heights_ordered[[1]] / 2)
  if (length(positioned) > 1L) {
    for (index in 2:length(positioned)) {
      minimum <- positioned[[index - 1L]] +
        heights_ordered[[index - 1L]] / 2 + heights_ordered[[index]] / 2 + gap
      positioned[[index]] <- max(desired_ordered[[index]], minimum)
    }
  }

  last <- length(positioned)
  positioned[[last]] <- min(positioned[[last]], upper - heights_ordered[[last]] / 2)
  if (last > 1L) {
    for (index in seq.int(last - 1L, 1L)) {
      maximum <- positioned[[index + 1L]] -
        heights_ordered[[index + 1L]] / 2 - heights_ordered[[index]] / 2 - gap
      positioned[[index]] <- min(positioned[[index]], maximum)
    }
  }
  if (positioned[[1]] < lower + heights_ordered[[1]] / 2 - 1e-9) {
    stop("Sankey label packing exceeded the lower panel boundary.", call. = FALSE)
  }
  output <- numeric(length(desired))
  output[order_index] <- positioned
  output
}

measure_node_labels <- function(nodes, config, font_family) {
  font_size <- as.numeric(config$sankey$label_font_size_pt)
  wrap_width <- as.integer(config$sankey$label_wrap_characters)
  line_height <- as.numeric(config$sankey$label_line_height)
  padding_mm <- as.numeric(config$sankey$label_padding_mm)
  nodes$wrapped_label <- vapply(nodes$display_label, function(label) {
    stringr::str_wrap(label, width = wrap_width)
  }, character(1))
  nodes$label <- paste0(
    nodes$wrapped_label,
    "\n",
    scales::comma(nodes$node_value, accuracy = 1)
  )
  measurement <- lapply(nodes$label, function(label) {
    lines <- strsplit(label, "\n", fixed = TRUE)[[1]]
    width_points <- max(systemfonts::string_width(
      lines,
      family = font_family,
      size = font_size
    ))
    list(
      width_mm = width_points * 25.4 / 72 + 2 * padding_mm,
      height_mm = length(lines) * font_size * line_height * 25.4 / 72 + 2 * padding_mm,
      line_count = length(lines)
    )
  })
  nodes$label_width_mm <- vapply(measurement, `[[`, numeric(1), "width_mm")
  nodes$label_height_mm <- vapply(measurement, `[[`, numeric(1), "height_mm")
  nodes$label_line_count <- vapply(measurement, `[[`, integer(1), "line_count")
  nodes
}

label_collision_pairs <- function(layout, tolerance = 1e-8) {
  if (nrow(layout) < 2L) {
    return(tibble::tibble(node_a = character(), node_b = character()))
  }
  pairs <- utils::combn(seq_len(nrow(layout)), 2L)
  collides <- apply(pairs, 2L, function(index) {
    a <- layout[index[[1]], ]
    b <- layout[index[[2]], ]
    x_overlap <- min(a$label_xmax, b$label_xmax) - max(a$label_xmin, b$label_xmin)
    y_overlap <- min(a$label_ymax, b$label_ymax) - max(a$label_ymin, b$label_ymin)
    x_overlap > tolerance && y_overlap > tolerance
  })
  selected <- pairs[, collides, drop = FALSE]
  if (ncol(selected) == 0L) {
    return(tibble::tibble(node_a = character(), node_b = character()))
  }
  tibble::tibble(
    node_a = layout$node_id[selected[1, ]],
    node_b = layout$node_id[selected[2, ]]
  )
}

label_node_collision_pairs <- function(layout, node_width, tolerance = 1e-8) {
  collisions <- list()
  collision_index <- 0L
  for (label_index in seq_len(nrow(layout))) {
    for (node_index in seq_len(nrow(layout))) {
      x_overlap <- min(
        layout$label_xmax[[label_index]],
        layout$x[[node_index]] + node_width / 2
      ) - max(
        layout$label_xmin[[label_index]],
        layout$x[[node_index]] - node_width / 2
      )
      y_overlap <- min(
        layout$label_ymax[[label_index]],
        layout$ymax[[node_index]]
      ) - max(
        layout$label_ymin[[label_index]],
        layout$ymin[[node_index]]
      )
      if (x_overlap > tolerance && y_overlap > tolerance) {
        collision_index <- collision_index + 1L
        collisions[[collision_index]] <- tibble::tibble(
          label_node_id = layout$node_id[[label_index]],
          obscured_node_id = layout$node_id[[node_index]]
        )
      }
    }
  }
  if (length(collisions) == 0L) {
    return(tibble::tibble(
      label_node_id = character(),
      obscured_node_id = character()
    ))
  }
  dplyr::bind_rows(collisions)
}

segment_is_horizontal <- function(segment, tolerance = 1e-8) {
  abs(segment$yend - segment$y) <= tolerance
}

segment_is_vertical <- function(segment, tolerance = 1e-8) {
  abs(segment$xend - segment$x) <= tolerance
}

segments_intersect <- function(a, b, tolerance = 1e-8) {
  a_horizontal <- segment_is_horizontal(a, tolerance)
  b_horizontal <- segment_is_horizontal(b, tolerance)
  a_vertical <- segment_is_vertical(a, tolerance)
  b_vertical <- segment_is_vertical(b, tolerance)
  if ((!a_horizontal && !a_vertical) || (!b_horizontal && !b_vertical)) {
    return(TRUE)
  }

  if (a_horizontal && b_horizontal) {
    overlap <- min(max(a$x, a$xend), max(b$x, b$xend)) -
      max(min(a$x, a$xend), min(b$x, b$xend))
    return(abs(a$y - b$y) <= tolerance && overlap > tolerance)
  }
  if (a_vertical && b_vertical) {
    overlap <- min(max(a$y, a$yend), max(b$y, b$yend)) -
      max(min(a$y, a$yend), min(b$y, b$yend))
    return(abs(a$x - b$x) <= tolerance && overlap > tolerance)
  }

  horizontal <- if (a_horizontal) a else b
  vertical <- if (a_vertical) a else b
  vertical$x >= min(horizontal$x, horizontal$xend) - tolerance &&
    vertical$x <= max(horizontal$x, horizontal$xend) + tolerance &&
    horizontal$y >= min(vertical$y, vertical$yend) - tolerance &&
    horizontal$y <= max(vertical$y, vertical$yend) + tolerance
}

connector_intersection_pairs <- function(segments, tolerance = 1e-8) {
  if (nrow(segments) < 2L) {
    return(tibble::tibble(
      connector_a = character(), segment_a = integer(),
      connector_b = character(), segment_b = integer()
    ))
  }
  collisions <- list()
  collision_index <- 0L
  pairs <- utils::combn(seq_len(nrow(segments)), 2L)
  for (pair_index in seq_len(ncol(pairs))) {
    a_index <- pairs[[1, pair_index]]
    b_index <- pairs[[2, pair_index]]
    if (segments$connector_id[[a_index]] == segments$connector_id[[b_index]]) {
      next
    }
    if (segments_intersect(
      segments[a_index, , drop = FALSE],
      segments[b_index, , drop = FALSE],
      tolerance
    )) {
      collision_index <- collision_index + 1L
      collisions[[collision_index]] <- tibble::tibble(
        connector_a = segments$connector_id[[a_index]],
        segment_a = segments$segment_index[[a_index]],
        connector_b = segments$connector_id[[b_index]],
        segment_b = segments$segment_index[[b_index]]
      )
    }
  }
  if (length(collisions) == 0L) {
    return(tibble::tibble(
      connector_a = character(), segment_a = integer(),
      connector_b = character(), segment_b = integer()
    ))
  }
  dplyr::bind_rows(collisions)
}

segment_centerline_distance_mm <- function(
  a,
  b,
  x_mm_per_data,
  y_mm_per_data
) {
  a_x <- sort(c(a$x, a$xend)) * x_mm_per_data
  a_y <- sort(c(a$y, a$yend)) * y_mm_per_data
  b_x <- sort(c(b$x, b$xend)) * x_mm_per_data
  b_y <- sort(c(b$y, b$yend)) * y_mm_per_data
  x_gap <- max(0, max(a_x[[1]], b_x[[1]]) - min(a_x[[2]], b_x[[2]]))
  y_gap <- max(0, max(a_y[[1]], b_y[[1]]) - min(a_y[[2]], b_y[[2]]))
  sqrt(x_gap^2 + y_gap^2)
}

connector_pair_clearances <- function(
  segments,
  line_width_mm,
  x_mm_per_data,
  y_mm_per_data
) {
  if (nrow(segments) < 2L) {
    return(tibble::tibble(
      connector_a = character(), segment_a = integer(),
      connector_b = character(), segment_b = integer(),
      centerline_distance_mm = numeric(), ink_clearance_mm = numeric()
    ))
  }
  clearances <- list()
  clearance_index <- 0L
  pairs <- utils::combn(seq_len(nrow(segments)), 2L)
  for (pair_index in seq_len(ncol(pairs))) {
    a_index <- pairs[[1, pair_index]]
    b_index <- pairs[[2, pair_index]]
    if (segments$connector_id[[a_index]] == segments$connector_id[[b_index]]) {
      next
    }
    centerline_distance <- segment_centerline_distance_mm(
      segments[a_index, , drop = FALSE],
      segments[b_index, , drop = FALSE],
      x_mm_per_data,
      y_mm_per_data
    )
    clearance_index <- clearance_index + 1L
    clearances[[clearance_index]] <- tibble::tibble(
      connector_a = segments$connector_id[[a_index]],
      segment_a = segments$segment_index[[a_index]],
      connector_b = segments$connector_id[[b_index]],
      segment_b = segments$segment_index[[b_index]],
      centerline_distance_mm = centerline_distance,
      ink_clearance_mm = centerline_distance - line_width_mm
    )
  }
  if (length(clearances) == 0L) {
    return(tibble::tibble(
      connector_a = character(), segment_a = integer(),
      connector_b = character(), segment_b = integer(),
      centerline_distance_mm = numeric(), ink_clearance_mm = numeric()
    ))
  }
  dplyr::bind_rows(clearances)
}

connector_clearance_violations <- function(
  segments,
  line_width_mm,
  minimum_ink_clearance_mm,
  x_mm_per_data,
  y_mm_per_data,
  tolerance = 1e-8
) {
  connector_pair_clearances(
    segments,
    line_width_mm,
    x_mm_per_data,
    y_mm_per_data
  ) |>
    dplyr::filter(
      .data$ink_clearance_mm < minimum_ink_clearance_mm - tolerance
    )
}

connector_segment_sets_clear <- function(
  segments_a,
  segments_b,
  line_width_mm,
  minimum_ink_clearance_mm,
  x_mm_per_data,
  y_mm_per_data,
  tolerance = 1e-8
) {
  if (nrow(segments_a) == 0L || nrow(segments_b) == 0L) {
    return(TRUE)
  }
  minimum_centerline_distance_mm <-
    line_width_mm + minimum_ink_clearance_mm
  for (a_index in seq_len(nrow(segments_a))) {
    for (b_index in seq_len(nrow(segments_b))) {
      if (segments_a$connector_id[[a_index]] ==
          segments_b$connector_id[[b_index]]) {
        next
      }
      distance_mm <- segment_centerline_distance_mm(
        segments_a[a_index, , drop = FALSE],
        segments_b[b_index, , drop = FALSE],
        x_mm_per_data,
        y_mm_per_data
      )
      if (distance_mm < minimum_centerline_distance_mm - tolerance) {
        return(FALSE)
      }
    }
  }
  TRUE
}

make_connector_segments <- function(node, lane_x = NA_real_, tolerance = 1e-8) {
  moved <- abs(node$label_y - node$ymid) > tolerance
  if (!moved) {
    points <- tibble::tibble(
      x = c(node$node_anchor_x, node$label_anchor_x),
      y = c(node$ymid, node$label_y)
    )
  } else {
    points <- tibble::tibble(
      x = c(node$node_anchor_x, lane_x, lane_x, node$label_anchor_x),
      y = c(node$ymid, node$ymid, node$label_y, node$label_y)
    )
  }
  segments <- tibble::tibble(
    connector_id = node$node_id,
    layer = node$layer,
    segment_index = seq_len(nrow(points) - 1L),
    x = points$x[-nrow(points)],
    y = points$y[-nrow(points)],
    xend = points$x[-1L],
    yend = points$y[-1L],
    lane_x = if (moved) lane_x else NA_real_,
    label_mode = node$label_mode
  )
  segments |>
    dplyr::filter(
      abs(.data$xend - .data$x) > tolerance |
        abs(.data$yend - .data$y) > tolerance
    ) |>
    dplyr::mutate(segment_index = dplyr::row_number())
}

route_label_connectors <- function(
  nodes,
  config,
  x_mm_per_data,
  y_mm_per_data,
  tolerance = 1e-8
) {
  line_width_mm <- as.numeric(config$sankey$connector_linewidth_mm)
  minimum_ink_clearance_mm <- as.numeric(
    config$sankey$connector_min_ink_clearance_mm
  )
  track_edge_margin_mm <- as.numeric(config$sankey$connector_track_edge_margin_mm)
  track_spacing_mm <- line_width_mm + minimum_ink_clearance_mm
  if (any(!is.finite(c(
    line_width_mm,
    minimum_ink_clearance_mm,
    track_edge_margin_mm,
    track_spacing_mm
  ))) || line_width_mm <= 0 || minimum_ink_clearance_mm < 0 ||
      track_edge_margin_mm < 0 || track_spacing_mm <= 0) {
    stop("Sankey connector physical-clearance settings are invalid.", call. = FALSE)
  }
  selected <- tibble::tibble()
  for (layer_id in sort(unique(nodes$layer))) {
    layer_nodes <- nodes[nodes$layer == layer_id, , drop = FALSE]
    direct_rows <- which(abs(layer_nodes$label_y - layer_nodes$ymid) <= tolerance)
    if (length(direct_rows) > 0L) {
      for (row_index in direct_rows) {
        selected <- dplyr::bind_rows(
          selected,
          make_connector_segments(layer_nodes[row_index, , drop = FALSE])
        )
      }
    }

    moved_rows <- which(abs(layer_nodes$label_y - layer_nodes$ymid) > tolerance)
    if (length(moved_rows) == 0L) {
      next
    }
    moved_rows <- moved_rows[order(
      layer_nodes$node_order[moved_rows],
      layer_nodes$node_id[moved_rows]
    )]
    existing <- if ("layer" %in% names(selected)) {
      selected[selected$layer == layer_id, , drop = FALSE]
    } else {
      tibble::tibble()
    }
    candidate_sets <- vector("list", length(moved_rows))
    names(candidate_sets) <- layer_nodes$node_id[moved_rows]
    for (route_index in seq_along(moved_rows)) {
      row_index <- moved_rows[[route_index]]
      node <- layer_nodes[row_index, , drop = FALSE]
      available_track_width_mm <- node$connector_span_mm -
        2 * track_edge_margin_mm
      if (available_track_width_mm < -tolerance) {
        stop(
          "A Sankey connector span is smaller than its two edge margins.",
          call. = FALSE
        )
      }
      track_count <- max(
        1L,
        floor(max(available_track_width_mm, 0) / track_spacing_mm) + 1L
      )
      track_offsets_mm <- if (track_count == 1L) {
        node$connector_span_mm / 2
      } else {
        seq(
          track_edge_margin_mm,
          node$connector_span_mm - track_edge_margin_mm,
          length.out = track_count
        )
      }
      direction <- if (node$label_anchor_x > node$node_anchor_x) 1 else -1
      candidate_lanes <- node$node_anchor_x +
        direction * track_offsets_mm / x_mm_per_data
      midpoint <- mean(c(node$node_anchor_x, node$label_anchor_x))
      candidate_lanes <- candidate_lanes[order(abs(candidate_lanes - midpoint))]
      candidates <- lapply(candidate_lanes, function(lane_x) {
        make_connector_segments(node, lane_x, tolerance)
      })
      candidate_is_clear <- vapply(candidates, function(candidate) {
        connector_segment_sets_clear(
          existing,
          candidate,
          line_width_mm,
          minimum_ink_clearance_mm,
          x_mm_per_data,
          y_mm_per_data,
          tolerance
        )
      }, logical(1))
      candidate_sets[[route_index]] <- candidates[candidate_is_clear]
      if (length(candidate_sets[[route_index]]) == 0L) {
        stop(
          "Sankey layer ", layer_id, " has no clear connector track for ",
          node$node_id, ". Increase connector_span_mm_by_layer.",
          call. = FALSE
        )
      }
    }

    route_count <- length(candidate_sets)
    compatibility <- matrix(
      vector("list", route_count * route_count),
      nrow = route_count,
      ncol = route_count
    )
    if (route_count > 1L) {
      for (route_a in seq_len(route_count - 1L)) {
        for (route_b in seq.int(route_a + 1L, route_count)) {
          pair_matrix <- matrix(
            FALSE,
            nrow = length(candidate_sets[[route_a]]),
            ncol = length(candidate_sets[[route_b]])
          )
          for (candidate_a in seq_along(candidate_sets[[route_a]])) {
            for (candidate_b in seq_along(candidate_sets[[route_b]])) {
              pair_matrix[candidate_a, candidate_b] <-
                connector_segment_sets_clear(
                  candidate_sets[[route_a]][[candidate_a]],
                  candidate_sets[[route_b]][[candidate_b]],
                  line_width_mm,
                  minimum_ink_clearance_mm,
                  x_mm_per_data,
                  y_mm_per_data,
                  tolerance
                )
            }
          }
          compatibility[[route_a, route_b]] <- pair_matrix
          compatibility[[route_b, route_a]] <- t(pair_matrix)
        }
      }
    }

    search_states <- 0L
    search_limit <- 200000L
    assignments <- rep(NA_integer_, route_count)
    solve_routes <- function(remaining) {
      search_states <<- search_states + 1L
      if (search_states > search_limit) {
        return(NULL)
      }
      if (length(remaining) == 0L) {
        return(assignments)
      }
      feasible <- lapply(remaining, function(route_index) {
        candidate_indices <- seq_along(candidate_sets[[route_index]])
        assigned_routes <- which(!is.na(assignments))
        for (assigned_route in assigned_routes) {
          candidate_indices <- candidate_indices[
            compatibility[[route_index, assigned_route]][
              candidate_indices,
              assignments[[assigned_route]]
            ]
          ]
          if (length(candidate_indices) == 0L) {
            break
          }
        }
        candidate_indices
      })
      feasible_counts <- lengths(feasible)
      if (any(feasible_counts == 0L)) {
        return(NULL)
      }
      selected_position <- which.min(feasible_counts)
      route_index <- remaining[[selected_position]]
      next_remaining <- remaining[-selected_position]
      for (candidate_index in feasible[[selected_position]]) {
        assignments[[route_index]] <<- candidate_index
        result <- solve_routes(next_remaining)
        if (!is.null(result)) {
          return(result)
        }
        assignments[[route_index]] <<- NA_integer_
      }
      NULL
    }
    layer_assignment <- solve_routes(seq_along(candidate_sets))
    if (is.null(layer_assignment)) {
      stop(
        "Sankey layer ", layer_id,
        " has no joint connector routing with the configured physical clearance ",
        "after ", search_states, " search states. Increase its connector span.",
        call. = FALSE
      )
    }
    layer_solution <- dplyr::bind_rows(lapply(
      seq_along(candidate_sets),
      function(route_index) {
        candidate_sets[[route_index]][[layer_assignment[[route_index]]]]
      }
    ))
    solution_violations <- connector_clearance_violations(
      dplyr::bind_rows(existing, layer_solution),
      line_width_mm,
      minimum_ink_clearance_mm,
      x_mm_per_data,
      y_mm_per_data,
      tolerance
    )
    if (nrow(solution_violations) > 0L) {
      stop(
        "Internal connector routing error in Sankey layer ", layer_id, ".",
        call. = FALSE
      )
    }
    selected <- dplyr::bind_rows(selected, layer_solution)
  }
  selected |>
    dplyr::arrange(.data$layer, .data$connector_id, .data$segment_index)
}

segment_rectangle_intersects <- function(segment, xmin, xmax, ymin, ymax, tolerance = 1e-8) {
  if (segment_is_horizontal(segment, tolerance)) {
    overlap <- min(max(segment$x, segment$xend), xmax) -
      max(min(segment$x, segment$xend), xmin)
    return(
      segment$y > ymin + tolerance && segment$y < ymax - tolerance &&
        overlap > tolerance
    )
  }
  if (segment_is_vertical(segment, tolerance)) {
    overlap <- min(max(segment$y, segment$yend), ymax) -
      max(min(segment$y, segment$yend), ymin)
    return(
      segment$x > xmin + tolerance && segment$x < xmax - tolerance &&
        overlap > tolerance
    )
  }
  TRUE
}

connector_rectangle_collisions <- function(
  segments,
  rectangles,
  rectangle_id,
  xmin,
  xmax,
  ymin,
  ymax,
  skip_own = TRUE,
  tolerance = 1e-8
) {
  collisions <- list()
  collision_index <- 0L
  for (segment_index in seq_len(nrow(segments))) {
    for (rectangle_index in seq_len(nrow(rectangles))) {
      current_rectangle_id <- rectangles[[rectangle_id]][[rectangle_index]]
      if (skip_own && segments$connector_id[[segment_index]] == current_rectangle_id) {
        next
      }
      if (segment_rectangle_intersects(
        segments[segment_index, , drop = FALSE],
        rectangles[[xmin]][[rectangle_index]],
        rectangles[[xmax]][[rectangle_index]],
        rectangles[[ymin]][[rectangle_index]],
        rectangles[[ymax]][[rectangle_index]],
        tolerance
      )) {
        collision_index <- collision_index + 1L
        collisions[[collision_index]] <- tibble::tibble(
          connector_id = segments$connector_id[[segment_index]],
          segment_index = segments$segment_index[[segment_index]],
          rectangle_id = current_rectangle_id
        )
      }
    }
  }
  if (length(collisions) == 0L) {
    return(tibble::tibble(
      connector_id = character(),
      segment_index = integer(),
      rectangle_id = character()
    ))
  }
  dplyr::bind_rows(collisions)
}

connector_orthogonality_violations <- function(segments, tolerance = 1e-8) {
  segments |>
    dplyr::filter(
      abs(.data$xend - .data$x) > tolerance &
        abs(.data$yend - .data$y) > tolerance
    ) |>
    dplyr::select(connector_id, segment_index, x, y, xend, yend)
}

node_order_violations <- function(nodes) {
  violations <- list()
  violation_index <- 0L
  for (layer_id in sort(unique(nodes$layer))) {
    layer_nodes <- nodes[nodes$layer == layer_id, , drop = FALSE] |>
      dplyr::arrange(.data$node_order)
    policy <- unique(layer_nodes$order_policy)
    if (length(policy) != 1L) {
      stop("Each Sankey layer must declare one ordering policy.", call. = FALSE)
    }
    checked <- if (policy == "size_desc") {
      layer_nodes
    } else if (policy == "eligible_then_size_desc") {
      if (layer_nodes$node_id[[1]] != "qsar:eligible") {
        violation_index <- violation_index + 1L
        violations[[violation_index]] <- tibble::tibble(
          layer = layer_id,
          order_policy = policy,
          upper_node_id = layer_nodes$node_id[[1]],
          upper_value = layer_nodes$node_value[[1]],
          lower_node_id = "qsar:eligible",
          lower_value = layer_nodes$node_value[layer_nodes$node_id == "qsar:eligible"][[1]],
          issue = "QSAR eligible is not the first node"
        )
      }
      layer_nodes[layer_nodes$node_id != "qsar:eligible", , drop = FALSE]
    } else {
      layer_nodes[0, , drop = FALSE]
    }
    if (nrow(checked) < 2L) {
      next
    }
    for (row_index in seq_len(nrow(checked) - 1L)) {
      if (checked$node_value[[row_index + 1L]] > checked$node_value[[row_index]]) {
        violation_index <- violation_index + 1L
        violations[[violation_index]] <- tibble::tibble(
          layer = layer_id,
          order_policy = policy,
          upper_node_id = checked$node_id[[row_index]],
          upper_value = checked$node_value[[row_index]],
          lower_node_id = checked$node_id[[row_index + 1L]],
          lower_value = checked$node_value[[row_index + 1L]],
          issue = "Larger node appears below a smaller node"
        )
      }
    }
  }
  if (length(violations) == 0L) {
    return(tibble::tibble(
      layer = integer(), order_policy = character(),
      upper_node_id = character(), upper_value = numeric(),
      lower_node_id = character(), lower_value = numeric(),
      issue = character()
    ))
  }
  dplyr::bind_rows(violations)
}

prepare_sankey_geometry <- function(edges, nodes, config, font_family) {
  node_gap <- as.numeric(config$sankey$node_gap_fraction)
  node_width <- as.numeric(config$sankey$node_width)
  layer_totals <- nodes |>
    dplyr::group_by(.data$layer) |>
    dplyr::summarise(total = sum(.data$node_value), count = dplyr::n(), .groups = "drop")
  maximum_total <- max(layer_totals$total)
  gap_value <- maximum_total * node_gap
  layer_totals <- layer_totals |>
    dplyr::mutate(extent = .data$total + pmax(.data$count - 1L, 0L) * gap_value)
  top_y <- max(layer_totals$extent)

  nodes <- nodes |>
    dplyr::arrange(.data$layer, .data$node_order, .data$node_id) |>
    dplyr::mutate(ymin = NA_real_, ymax = NA_real_)
  for (layer_id in sort(unique(nodes$layer))) {
    rows <- which(nodes$layer == layer_id)
    cursor <- top_y
    for (row in rows) {
      nodes$ymax[[row]] <- cursor
      nodes$ymin[[row]] <- cursor - nodes$node_value[[row]]
      cursor <- nodes$ymin[[row]] - gap_value
    }
  }
  nodes <- nodes |>
    dplyr::mutate(
      ymin = .data$ymin / top_y,
      ymax = .data$ymax / top_y,
      ymid = (.data$ymin + .data$ymax) / 2,
      x = as.numeric(.data$layer)
    )

  lookup <- nodes |>
    dplyr::select(
      node_id, layer, node_order, node_color, x, ymin, ymax, ymid
    )
  edges <- edges |>
    dplyr::mutate(edge_id = dplyr::row_number()) |>
    dplyr::left_join(lookup, by = c("source_id" = "node_id")) |>
    dplyr::rename_with(~paste0("source_", .x), c(
      "layer", "node_order", "node_color", "x", "ymin", "ymax", "ymid"
    )) |>
    dplyr::left_join(lookup, by = c("target_id" = "node_id")) |>
    dplyr::rename_with(~paste0("target_", .x), c(
      "layer", "node_order", "node_color", "x", "ymin", "ymax", "ymid"
    )) |>
    dplyr::arrange(
      .data$source_layer, .data$source_node_order,
      .data$target_layer, .data$target_node_order, .data$target_id
    )
  if (any(is.na(edges$source_layer)) || any(is.na(edges$target_layer))) {
    stop("Sankey edges reference one or more missing nodes.", call. = FALSE)
  }
  edges <- edges |>
    dplyr::mutate(
      edge_fraction = .data$value / top_y,
      ribbon_color = dplyr::case_when(
        .data$stage == "source_to_identifier" ~ .data$source_node_color,
        .data$stage == "identifier_to_recovery" ~ .data$target_node_color,
        .data$stage == "recovery_to_resolution" ~ .data$source_node_color,
        grepl("unresolved", .data$target_id, fixed = TRUE) ~ "#AEB5BB",
        .data$target_id == "dedup:collapsed_records" ~ "#B7A4B9",
        grepl("^qsar:", .data$target_id) & .data$target_id != "qsar:eligible" ~ "#AEB5BB",
        TRUE ~ "#4F8FC5"
      ),
      ribbon_alpha = dplyr::case_when(
        .data$stage == "source_to_identifier" ~ 0.30,
        .data$stage %in% c("identifier_to_recovery", "recovery_to_resolution") ~ 0.36,
        TRUE ~ 0.48
      ),
      source_flow_ymin = NA_real_,
      source_flow_ymax = NA_real_,
      target_flow_ymin = NA_real_,
      target_flow_ymax = NA_real_
    )
  for (node_id in unique(edges$source_id)) {
    rows <- which(edges$source_id == node_id)
    rows <- rows[order(edges$target_layer[rows], edges$target_node_order[rows], edges$target_id[rows])]
    cursor <- unique(edges$source_ymin[rows])[[1]]
    for (row in rows) {
      edges$source_flow_ymin[[row]] <- cursor
      edges$source_flow_ymax[[row]] <- cursor + edges$edge_fraction[[row]]
      cursor <- edges$source_flow_ymax[[row]]
    }
  }
  for (node_id in unique(edges$target_id)) {
    rows <- which(edges$target_id == node_id)
    rows <- rows[order(edges$source_layer[rows], edges$source_node_order[rows], edges$source_id[rows])]
    cursor <- unique(edges$target_ymin[rows])[[1]]
    for (row in rows) {
      edges$target_flow_ymin[[row]] <- cursor
      edges$target_flow_ymax[[row]] <- cursor + edges$edge_fraction[[row]]
      cursor <- edges$target_flow_ymax[[row]]
    }
  }

  make_ribbon <- function(row, points = 60L) {
    parameter <- seq(0, 1, length.out = points)
    x0 <- row$source_x + node_width / 2
    x1 <- row$target_x - node_width / 2
    distance <- x1 - x0
    control0 <- x0 + distance * 0.44
    control1 <- x1 - distance * 0.44
    x_values <- bezier_value(x0, control0, control1, x1, parameter)
    y_top <- bezier_value(
      row$source_flow_ymax, row$source_flow_ymax,
      row$target_flow_ymax, row$target_flow_ymax, parameter
    )
    y_bottom <- bezier_value(
      row$source_flow_ymin, row$source_flow_ymin,
      row$target_flow_ymin, row$target_flow_ymin, parameter
    )
    tibble::tibble(
      edge_id = row$edge_id,
      x = c(x_values, rev(x_values)),
      y = c(y_top, rev(y_bottom)),
      ribbon_color = row$ribbon_color,
      ribbon_alpha = row$ribbon_alpha
    )
  }
  ribbons <- dplyr::bind_rows(lapply(seq_len(nrow(edges)), function(index) {
    make_ribbon(edges[index, , drop = FALSE])
  }))

  nodes <- measure_node_labels(nodes, config, font_family)
  flow_height_mm <- as.numeric(config$sankey$flow_height_mm)
  panel_width_mm <- as.numeric(config$export$width_mm) - 10
  if (!is.finite(panel_width_mm) || panel_width_mm <= 0) {
    stop("Configured figure width is too small for Sankey label measurement.", call. = FALSE)
  }
  nodes$label_height_fraction <- nodes$label_height_mm / flow_height_mm
  nodes$label_y <- nodes$ymid
  gap_fraction <- as.numeric(config$sankey$label_gap_mm) / flow_height_mm
  for (layer_id in sort(unique(nodes$layer))) {
    rows <- which(nodes$layer == layer_id)
    nodes$label_y[rows] <- pack_label_centres(
      nodes$ymid[rows],
      nodes$label_height_fraction[rows],
      gap = gap_fraction
    )
  }
  label_sides <- unlist(config$sankey$label_side_by_layer, use.names = TRUE)
  observed_sides <- unname(label_sides[as.character(nodes$layer)])
  if (any(is.na(observed_sides)) || any(!observed_sides %in% c("left", "right"))) {
    stop(
      "figure.yml must declare a left/right Sankey label side for every layer.",
      call. = FALSE
    )
  }
  connector_spans <- unlist(
    config$sankey$connector_span_mm_by_layer,
    use.names = TRUE
  )
  observed_connector_spans <- as.numeric(
    connector_spans[as.character(nodes$layer)]
  )
  x_mm_per_data <- panel_width_mm / 7
  direct_height_ratio <- as.numeric(config$sankey$direct_label_height_ratio)
  if (any(!is.finite(observed_connector_spans)) ||
      any(observed_connector_spans <= 0) ||
      !is.finite(direct_height_ratio) || direct_height_ratio <= 0) {
    stop("Sankey label routing dimensions must be positive.", call. = FALSE)
  }
  nodes <- nodes |>
    dplyr::mutate(
      label_side = observed_sides,
      connector_span_mm = observed_connector_spans,
      connector_span_data = .data$connector_span_mm / x_mm_per_data,
      node_anchor_x = dplyr::if_else(
        .data$label_side == "left",
        .data$x - node_width / 2,
        .data$x + node_width / 2
      ),
      label_anchor_x = dplyr::if_else(
        .data$label_side == "left",
        .data$node_anchor_x - .data$connector_span_data,
        .data$node_anchor_x + .data$connector_span_data
      ),
      label_x = .data$label_anchor_x,
      hjust = dplyr::if_else(.data$label_side == "left", 1, 0),
      label_width_data = .data$label_width_mm * 7 / panel_width_mm,
      label_xmin = dplyr::case_when(
        .data$hjust == 1 ~ .data$label_x - .data$label_width_data,
        .data$hjust == 0 ~ .data$label_x,
        TRUE ~ .data$label_x - .data$label_width_data / 2
      ),
      label_xmax = .data$label_xmin + .data$label_width_data,
      label_ymin = .data$label_y - .data$label_height_fraction / 2,
      label_ymax = .data$label_y + .data$label_height_fraction / 2,
      label_move = abs(.data$label_y - .data$ymid),
      node_height_mm = (.data$ymax - .data$ymin) * flow_height_mm,
      label_mode = dplyr::if_else(
        .data$node_height_mm >= .data$label_height_mm * direct_height_ratio &
          .data$label_move <= 1e-8,
        "direct",
        "callout"
      ),
      node_xmin = .data$x - node_width / 2,
      node_xmax = .data$x + node_width / 2
    )
  connector_segments <- route_label_connectors(
    nodes,
    config,
    x_mm_per_data,
    flow_height_mm
  )
  line_width_mm <- as.numeric(config$sankey$connector_linewidth_mm)
  minimum_ink_clearance_mm <- as.numeric(
    config$sankey$connector_min_ink_clearance_mm
  )
  connector_clearances <- connector_pair_clearances(
    connector_segments,
    line_width_mm,
    x_mm_per_data,
    flow_height_mm
  )
  connector_clearance_failures <- connector_clearances |>
    dplyr::filter(
      .data$ink_clearance_mm < minimum_ink_clearance_mm - 1e-8
    )
  minimum_connector_ink_clearance_mm <- if (nrow(connector_clearances) == 0L) {
    Inf
  } else {
    min(connector_clearances$ink_clearance_mm)
  }
  connector_track_summary <- connector_segments |>
    dplyr::filter(
      abs(.data$xend - .data$x) <= 1e-8,
      abs(.data$yend - .data$y) > 1e-8
    ) |>
    dplyr::group_by(.data$layer) |>
    dplyr::summarise(
      vertical_connector_count = dplyr::n_distinct(.data$connector_id),
      allocated_track_count = dplyr::n_distinct(round(.data$lane_x, 12)),
      .groups = "drop"
    ) |>
    dplyr::left_join(
      nodes |>
        dplyr::distinct(.data$layer, .data$connector_span_mm),
      by = "layer"
    )
  label_collisions <- label_collision_pairs(nodes)
  label_node_collisions <- label_node_collision_pairs(nodes, node_width)
  connector_intersections <- connector_intersection_pairs(connector_segments)
  connector_node_collisions <- connector_rectangle_collisions(
    connector_segments,
    nodes,
    rectangle_id = "node_id",
    xmin = "node_xmin",
    xmax = "node_xmax",
    ymin = "ymin",
    ymax = "ymax"
  )
  connector_label_collisions <- connector_rectangle_collisions(
    connector_segments,
    nodes,
    rectangle_id = "node_id",
    xmin = "label_xmin",
    xmax = "label_xmax",
    ymin = "label_ymin",
    ymax = "label_ymax"
  )
  connector_orthogonality <- connector_orthogonality_violations(connector_segments)
  order_violations <- node_order_violations(nodes)
  list(
    nodes = nodes,
    edges = edges,
    ribbons = ribbons,
    connector_segments = connector_segments,
    connector_clearance_violations = connector_clearance_failures,
    connector_track_summary = connector_track_summary,
    minimum_connector_ink_clearance_mm = minimum_connector_ink_clearance_mm,
    label_collisions = label_collisions,
    label_node_collisions = label_node_collisions,
    connector_intersections = connector_intersections,
    connector_node_collisions = connector_node_collisions,
    connector_label_collisions = connector_label_collisions,
    connector_orthogonality = connector_orthogonality,
    order_violations = order_violations
  )
}

plot_identity_resolution_flow <- function(edges, nodes, config) {
  font_family <- resolve_manuscript_font()
  geometry <- prepare_sankey_geometry(edges, nodes, config, font_family)
  plot_nodes <- geometry$nodes
  stage_labels <- tibble::tibble(
    x = 1:6,
    label = c(
      "Source databases\nrecords",
      "Reported identifier\nrecords",
      "Recovery route\nrecords",
      "Resolution\nrecords",
      "Deduplication\nrecords → compounds",
      "QSAR eligibility\ncompounds"
    )
  )
  node_width <- as.numeric(config$sankey$node_width)
  font_size <- as.numeric(config$sankey$label_font_size_pt) / ggplot2::.pt

  panel <- ggplot2::ggplot() +
    ggplot2::geom_polygon(
      data = geometry$ribbons,
      ggplot2::aes(
        x = .data$x, y = .data$y, group = .data$edge_id,
        fill = .data$ribbon_color, alpha = .data$ribbon_alpha
      ),
      colour = NA
    ) +
    ggplot2::geom_segment(
      data = geometry$connector_segments,
      ggplot2::aes(
        x = .data$x, xend = .data$xend,
        y = .data$y, yend = .data$yend
      ),
      colour = "#66727E",
      linewidth = as.numeric(config$sankey$connector_linewidth_mm),
      lineend = "square"
    ) +
    ggplot2::geom_rect(
      data = plot_nodes,
      ggplot2::aes(
        xmin = .data$x - node_width / 2,
        xmax = .data$x + node_width / 2,
        ymin = .data$ymin,
        ymax = .data$ymax,
        fill = .data$node_color
      ),
      colour = "#45515D",
      linewidth = 0.18
    ) +
    ggplot2::geom_label(
      data = plot_nodes,
      ggplot2::aes(
        x = .data$label_x, y = .data$label_y,
        label = .data$label, hjust = .data$hjust
      ),
      family = font_family,
      size = font_size,
      lineheight = as.numeric(config$sankey$label_line_height),
      label.padding = grid::unit(as.numeric(config$sankey$label_padding_mm), "mm"),
      label.r = grid::unit(0.3, "mm"),
      fill = "#FFFFFFE8",
      colour = "#17212B",
      linewidth = 0
    ) +
    ggplot2::geom_label(
      data = stage_labels,
      ggplot2::aes(x = .data$x, y = 1.075, label = .data$label),
      family = font_family,
      size = 5.4 / ggplot2::.pt,
      fontface = "bold",
      lineheight = 0.92,
      label.padding = grid::unit(1.0, "mm"),
      label.r = grid::unit(0.4, "mm"),
      fill = "#E8F2F7",
      colour = "#111820",
      linewidth = 0
    ) +
    ggplot2::scale_fill_identity() +
    ggplot2::scale_alpha_identity() +
    ggplot2::coord_cartesian(xlim = c(0, 7), ylim = c(-0.02, 1.11), clip = "off") +
    ggplot2::theme_void(base_family = font_family) +
    ggplot2::theme(
      plot.margin = ggplot2::margin(2, 3, 1, 3, unit = "mm"),
      plot.background = ggplot2::element_rect(fill = "white", colour = NA)
    )

  label_layout <- plot_nodes |>
    dplyr::select(
      node_id, display_label, layer, node_order, order_policy,
      node_value, label, label_x, label_y,
      label_side, label_mode, node_anchor_x, label_anchor_x,
      node_height_mm, connector_span_mm,
      label_width_mm, label_height_mm,
      label_xmin, label_xmax, label_ymin, label_ymax,
      label_move
    )
  list(
    plot = panel,
    label_layout = label_layout,
    connector_segments = geometry$connector_segments,
    connector_clearance_violations = geometry$connector_clearance_violations,
    connector_track_summary = geometry$connector_track_summary,
    minimum_connector_ink_clearance_mm = geometry$minimum_connector_ink_clearance_mm,
    label_collisions = geometry$label_collisions,
    label_node_collisions = geometry$label_node_collisions,
    connector_intersections = geometry$connector_intersections,
    connector_node_collisions = geometry$connector_node_collisions,
    connector_label_collisions = geometry$connector_label_collisions,
    connector_orthogonality = geometry$connector_orthogonality,
    order_violations = geometry$order_violations,
    plotted_nodes = plot_nodes,
    plotted_edges = geometry$edges
  )
}
