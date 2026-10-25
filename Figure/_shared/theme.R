resolve_manuscript_font <- function() {
  if (!requireNamespace("systemfonts", quietly = TRUE)) {
    return("sans")
  }
  families <- unique(systemfonts::system_fonts()$family)
  if (any(tolower(families) == "arial")) "Arial" else "sans"
}

theme_manuscript <- function(base_size = 7, base_family = resolve_manuscript_font()) {
  ggplot2::theme_classic(base_size = base_size, base_family = base_family) +
    ggplot2::theme(
      axis.line = ggplot2::element_line(linewidth = 0.35, colour = "#25313D"),
      axis.ticks = ggplot2::element_line(linewidth = 0.35, colour = "#25313D"),
      axis.title = ggplot2::element_text(size = base_size, colour = "#25313D"),
      axis.text = ggplot2::element_text(size = base_size - 0.5, colour = "#45515D"),
      legend.title = ggplot2::element_text(size = base_size - 0.2),
      legend.text = ggplot2::element_text(size = base_size - 0.6),
      strip.text = ggplot2::element_text(size = base_size, face = "bold"),
      plot.title = ggplot2::element_text(
        size = base_size + 1,
        face = "bold",
        colour = "#111820"
      ),
      plot.subtitle = ggplot2::element_text(
        size = base_size - 0.2,
        colour = "#5B6673"
      ),
      panel.grid = ggplot2::element_blank(),
      plot.background = ggplot2::element_rect(fill = "white", colour = NA),
      panel.background = ggplot2::element_rect(fill = "white", colour = NA)
    )
}

manuscript_tag_theme <- function(font_family = resolve_manuscript_font()) {
  ggplot2::theme(
    plot.tag = ggplot2::element_text(
      family = font_family,
      size = 9,
      face = "bold",
      colour = "#111820"
    )
  )
}
