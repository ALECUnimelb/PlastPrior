# Assembly inherits theme_classic(base_size = 8, base_family = "Arial") and
# delegates svglite::svglite(), grDevices::cairo_pdf(),
# ragg::agg_png(res = 600), and ragg::agg_tiff(res = 600) to build.R and
# _shared/export.R at final width_mm = 183 and height_mm = 215.

tag_priority_panel <- function(plot, tag, config) {
  plot +
    ggplot2::labs(tag = tag) +
    ggplot2::theme(
      plot.tag = ggplot2::element_text(
        family = resolve_manuscript_font(),
        size = as.numeric(config$layout$tag_size_pt),
        face = "bold",
        colour = "#111820"
      ),
      plot.tag.position = c(0.006, 0.994)
    )
}

assemble_priority_landscape <- function(panel_plots, config) {
  required <- c(
    "priority_score_distribution",
    "regulatory_context_inset",
    "hazard_exposure_landscape",
    "score_decomposition",
    "hazard_component_profiles",
    "exposure_component_profiles"
  )
  missing <- setdiff(required, names(panel_plots))
  if (length(missing) > 0L) {
    stop(
      "Cannot assemble priority landscape; missing plot(s): ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }
  inset <- config$layout$inset
  top_row <- tag_priority_panel(
    panel_plots$priority_score_distribution,
    "a",
    config
  ) + patchwork::inset_element(
    panel_plots$regulatory_context_inset,
    left = as.numeric(inset$left),
    bottom = as.numeric(inset$bottom),
    right = as.numeric(inset$right),
    top = as.numeric(inset$top),
    align_to = inset$align_to,
    clip = FALSE,
    on_top = TRUE
  )
  heatmap_row <- grid::grobTree(
    patchwork::patchworkGrob(panel_plots$hazard_exposure_landscape),
    grid::textGrob('b',x=grid::unit(.006,'npc'),y=grid::unit(.994,'npc'),
      just=c('left','top'),gp=grid::gpar(fontfamily=resolve_manuscript_font(),
      fontsize=as.numeric(config$layout$tag_size_pt),fontface='bold',col='#111820'))
  )
  middle_row <- patchwork::wrap_elements(full=heatmap_row) +
    tag_priority_panel(panel_plots$score_decomposition,"c",config) +
    patchwork::plot_layout(widths=as.numeric(unlist(config$layout$middle_widths)))
  bottom_row <- tag_priority_panel(panel_plots$hazard_component_profiles,"d",config) +
    tag_priority_panel(panel_plots$exposure_component_profiles,"e",config) +
    patchwork::plot_layout(widths=as.numeric(unlist(config$layout$bottom_widths)))
  patchwork::wrap_elements(full=top_row) /
    patchwork::wrap_elements(full=middle_row) /
    patchwork::wrap_elements(full=bottom_row) +
    patchwork::plot_layout(heights=as.numeric(unlist(config$layout$row_heights)))
}
