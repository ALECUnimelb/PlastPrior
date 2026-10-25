# Assembly inherits theme_classic(base_size = 7, base_family = "Arial") and
# delegates svglite::svglite("figure.svg"),
# grDevices::cairo_pdf("figure.pdf"), ragg::agg_png("figure.png", res = 600),
# and ragg::agg_tiff("figure.tiff", res = 600) to _shared/export.R at
# width_mm = 183.

assemble_evidence_overlap_patterns <- function(hazard_plot, exposure_plot) {
  require_r_packages(c("patchwork", "ggplot2"))
  hazard_panel <- patchwork::wrap_elements(full = hazard_plot)
  exposure_panel <- patchwork::wrap_elements(full = exposure_plot)
  hazard_panel / exposure_panel +
    patchwork::plot_layout(heights = c(0.95, 1.15)) +
    patchwork::plot_annotation(tag_levels = "a") &
    manuscript_tag_theme()
}
