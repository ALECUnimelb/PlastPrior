# Approved a / b / c+d layout. Export settings are in build.R.
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

assemble_priority_landscape_current <- function(plots,config) {
 inset <- config$layout$inset
 top <- tag_priority_panel(plots$priority_score_distribution,'a',config)+
 inset_element(plots$regulatory_context_inset,left=inset$left,bottom=inset$bottom,right=inset$right,top=inset$top,align_to=inset$align_to,clip=FALSE)
 middle <- grid::grobTree(patchworkGrob(plots$hazard_exposure_landscape),
 grid::textGrob('b',x=grid::unit(.006,'npc'),y=grid::unit(.994,'npc'),just=c('left','top'),gp=grid::gpar(fontfamily=resolve_manuscript_font(),fontsize=8.5,fontface='bold')))
 bottom <- tag_priority_panel(plots$hazard_component_profiles,'c',config)+
 tag_priority_panel(plots$exposure_component_profiles,'d',config)+plot_layout(widths=c(1,1))
 wrap_elements(full=top)/wrap_elements(full=middle)/wrap_elements(full=bottom)+plot_layout(heights=config$layout$row_heights)
}
