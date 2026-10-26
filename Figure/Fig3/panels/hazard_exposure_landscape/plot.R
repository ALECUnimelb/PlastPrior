# Approved numeric heatmap; all graphics use R, Arial, and editable vector exports.
plot_hazard_exposure_landscape <- function(panel_data, config, variant='publication') {
 compact <- identical(variant,'compact')
 style <- config$display$heatmap_compact
 pt_to_mm <- function(x) as.numeric(x) / (72.27/25.4)
 grid <- panel_data$heatmap_source_data
 key <- panel_data$colour_key
 x_labels <- as.character(0:16)
 priority_levels <- c('Low priority','Moderate priority','High priority')
 palettes <- lapply(priority_levels,function(p) key$colour[key$priority==p])
 names(palettes) <- priority_levels
boundaries <- data.frame(x=c(6,11,6),y=c(5,0,5),xend=c(6,11,17),yend=c(11,11,5))
p <- ggplot(grid,aes(x=hazard_position+.5,y=exposure_bin+.5)) +
 geom_tile(aes(fill=fill_colour),width=1,height=1,colour='white',linewidth=if(compact) style$tile_linewidth_mm else .4) +
 geom_segment(data=boundaries,aes(x=x,y=y,xend=xend,yend=yend),inherit.aes=FALSE,colour='white',linewidth=if(compact) .75 else 1.1) +
 geom_segment(data=boundaries,aes(x=x,y=y,xend=xend,yend=yend),inherit.aes=FALSE,colour='#243442',linewidth=if(compact) style$boundary_linewidth_mm else .5,linetype='22') +
 geom_text(aes(label=compound_count,colour=text_colour),family='Arial',size=if(compact) pt_to_mm(style$number_size_pt) else 2.9) +
 scale_colour_identity() + scale_fill_identity() +
 scale_x_continuous(breaks=(0:16)+.5,labels=x_labels,limits=c(0,17),expand=expansion(mult=0)) +
 scale_y_continuous(breaks=(0:10)+.5,labels=0:10,limits=c(0,11),expand=expansion(mult=0)) +
 coord_fixed(ratio=if(compact) style$cell_aspect_ratio else 1,clip='off') +
 labs(x='Hazard score (threshold-aware bins)',y='Exposure score (bins)') +
 theme_classic(base_size=if(compact) style$axis_title_size_pt else 10,base_family='Arial') +
 theme(axis.line=element_blank(),axis.ticks=element_blank(),axis.text=element_text(colour='#202830',size=if(compact) style$axis_text_size_pt else 8.5),axis.text.x=element_text(lineheight=.85),axis.title=element_text(colour='#202830'),plot.margin=if(compact) margin(5,3,1,3) else margin(6,8,1,8))
# Three ticks on a four-shade key: same count intervals as the heatmap.
legend_segments <- do.call(rbind,lapply(seq_along(priority_levels),function(i) {
 data.frame(x=(i-1)+.10+((1:4)-.5)*.20,colour=palettes[[priority_levels[i]]])
}))
legend_ticks <- do.call(rbind,lapply(0:2,function(i) {
 data.frame(x=i+c(.10,.50,.80),label=c('0','50','>100'))
}))
legend_labels <- data.frame(x=c(.5,1.5,2.5),label=priority_levels)
legend_plot <- ggplot() +
 geom_tile(data=legend_segments,aes(x=x,y=.55,fill=colour),width=.20,height=.24) +
 scale_fill_identity() +
 geom_segment(data=legend_ticks,aes(x=x,xend=x,y=.67,yend=.73),linewidth=.3,colour='#202830') +
 geom_text(data=legend_ticks,aes(x=x,y=.86,label=label),family='Arial',size=if(compact) pt_to_mm(style$legend_tick_size_pt) else 2.8,colour='#202830') +
 geom_text(data=legend_labels,aes(x=x,y=.14,label=label),family='Arial',size=if(compact) pt_to_mm(style$legend_label_size_pt) else 3.2,colour='#202830') +
 scale_x_continuous(limits=c(0,3),expand=expansion(mult=0)) +
 scale_y_continuous(limits=c(0,1),expand=expansion(mult=0)) +
 theme_void(base_family='Arial') + theme(plot.margin=if(compact) margin(0,1,0,1) else margin(0,8,0,8))
legend_row <- plot_spacer() + legend_plot + plot_spacer() + plot_layout(widths=if(compact) c(.1,8.8,.1) else c(1,7,1))
# Use the available vertical space for the heatmap; keep its key directly below.
combined <- if(compact) {
 (p / legend_row) + plot_layout(heights=as.numeric(unlist(style$row_heights))) +
   plot_annotation(theme=theme(plot.margin=margin(4,1,2,1)))
} else {
 (p / legend_row) + plot_layout(heights=c(12.7,1.6)) +
   plot_annotation(theme=theme(plot.margin=margin(4,4,4,4)))
}
 combined
}
