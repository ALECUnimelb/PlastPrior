assemble_source_assembly_and_overlap <- function(sankey_plot, upset_plot) {
  font_family <- resolve_manuscript_font()
  upset_wrapped <- patchwork::wrap_elements(full = upset_plot)
  sankey_plot / upset_wrapped +
    patchwork::plot_layout(heights = c(1.08, 1)) +
    patchwork::plot_annotation(tag_levels = "a") &
    ggplot2::theme(
      plot.tag = ggplot2::element_text(
        family = font_family,
        size = 8.5,
        face = "bold",
        colour = "#111820"
      ),
      plot.tag.position = c(0.006, 0.994)
    )
}
