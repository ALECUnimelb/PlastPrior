#!/usr/bin/env Rscript
# Preview contract: existing quantitative multipanel layout, all compounds,
# rounded domain scores and four priority levels. R-only rendering, Arial,
# editable SVG/PDF and 600 dpi PNG/TIFF via shared export_figure.
# Devices in Figure/_shared/export.R: svglite::svglite(), grDevices::cairo_pdf(),
# ragg::agg_png(res = 600), ragg::agg_tiff(res = 600).
# Full figure width_mm = 183, height_mm = 218; theme_classic(base_size = 8).
# Raw evidence profiles remain unweighted and distinguish missing from zero.
setwd('/Users/ruiwang/Projects/APPs/PlastPrior')
library(ggplot2)
library(patchwork)
for (f in c('theme.R','export.R')) source(file.path('Figure/_shared',f))
module_dir <- 'Figure/Fig3'
for(f in c('style.R','data.R','assemble.R')) source(file.path(module_dir,f))
ids <- c('priority_score_distribution','regulatory_context_inset','hazard_component_profiles','exposure_component_profiles')
for(id in ids) for(f in c('data.R','plot.R')) source(file.path(module_dir,'panels',id,f))
config <- jsonlite::fromJSON(file.path(module_dir,'figure.yml'),simplifyVector=FALSE)
priority_levels <- paste('Level',1:4)
config$priority_palette <- as.list(setNames(c('#A9463E','#C88736','#36495D','#AEB7C2'),priority_levels))
config$layout$row_heights <- c(65,85,68)
config$layout$inset$bottom <- .32
output_dir <- file.path(module_dir,'output/level4_preview_v3')
data_dir <- 'output/2026-10-27/figure_data/Fig3_preview_v3'
dir.create(output_dir,recursive=TRUE,showWarnings=FALSE)
dir.create(data_dir,recursive=TRUE,showWarnings=FALSE)
input <- 'output/2026-10-27/PlastPrior_results.csv'
stopifnot(sha256_file(input)=='280fde89c1f3ac2625dd963a6bdf44fd03833f42bb87acfd7fa06824b3fed637')
compounds <- as.data.frame(readr::read_csv(input,show_col_types=FALSE))
compounds$Inchikey_std <- compounds$inchikey
stopifnot(nrow(compounds)==15125, !anyDuplicated(compounds$inchikey))
level_for <- function(h,e) ifelse((h>=12 & e>=8)|(e>=12 & h>=8),1L,
  ifelse(h>=12|e>=12|(h>=8 & e>=8),2L,ifelse(h>=8|e>=8,3L,4L)))
stopifnot(all(compounds$Hazard_score==floor(compounds$Hazard_score_raw+0.5)),
 all(compounds$Exposure_score==floor(compounds$Exposure_score_raw+0.5)),
 all(compounds$Priority_score==compounds$Hazard_score+compounds$Exposure_score),
 all(compounds$Priority_level==level_for(compounds$Hazard_score,compounds$Exposure_score)),
 all(compounds$Priority_tier==paste('Level',compounds$Priority_level)),
 all(compounds$Hazard_score %in% 0:16),all(compounds$Exposure_score %in% 0:16))
compounds$GIC_regulatory_status_display <- unname(regulatory_status_map[compounds$GIC_regulatory_status])
stopifnot(!anyNA(compounds$GIC_regulatory_status_display))
metadata <- list(priority_score_min=min(compounds$Priority_score),priority_score_max=max(compounds$Priority_score),priority_score_median=median(compounds$Priority_score),priority_tier_counts=as.list(table(compounds$Priority_tier)))
save_tables <- function(tables,prefix='') {
 for(n in names(tables)) {
  p <- file.path(data_dir,prefix,paste0(n,'.csv'))
  if(is.data.frame(tables[[n]])) {dir.create(dirname(p),recursive=TRUE,showWarnings=FALSE);readr::write_csv(tables[[n]],p,na='')}
  else if(is.list(tables[[n]])) save_tables(tables[[n]],file.path(prefix,n))
 }
}
prepared <- list(priority_score_distribution=prepare_priority_score_distribution(compounds,metadata),
 regulatory_context_inset=prepare_regulatory_context_inset(compounds),
 hazard_component_profiles=prepare_hazard_component_profiles(compounds),exposure_component_profiles=prepare_exposure_component_profiles(compounds,metadata))
for(id in names(prepared)) save_tables(prepared[[id]]$source_data,id)
plot_priority_score_distribution <- function(panel_data,config,variant='publication') {
 d <- panel_data$priority_distribution
 d$Priority_tier <- factor(d$Priority_tier,levels=priority_levels)
 totals <- aggregate(compound_count~score_bin,d,sum)
 ggplot(d,aes(score_bin,compound_count,fill=Priority_tier))+
 geom_col(width=.82,colour='white',linewidth=.15)+
 scale_fill_manual(values=named_palette(config,'priority_palette'),breaks=priority_levels)+
 scale_x_continuous(breaks=seq(0,32,2),expand=expansion(add=.55))+
 scale_y_continuous(labels=scales::comma,limits=c(0,max(totals$compound_count)*1.65),expand=expansion(mult=c(0,0)))+
 geom_text(data=totals,aes(score_bin,compound_count,label=scales::comma(compound_count)),inherit.aes=FALSE,vjust=-.4,size=2,check_overlap=TRUE)+
 labs(x='Priority score (rounded H + rounded E)',y='Number of compounds')+
 priority_landscape_theme()+theme(legend.position='top',legend.justification='left')
}
grid_data <- expand.grid(Hazard_score=0:16,Exposure_score=0:16)
counts <- dplyr::count(compounds,Hazard_score,Exposure_score,name='compound_count')
grid_data <- merge(grid_data,counts,all.x=TRUE)
grid_data$compound_count[is.na(grid_data$compound_count)] <- 0L
grid_data$priority_level <- level_for(grid_data$Hazard_score,grid_data$Exposure_score)
grid_data$priority_tier <- paste('Level',grid_data$priority_level)
bands <- c('0–10','11–50','51–100','>100')
grid_data$count_band <- as.character(cut(grid_data$compound_count,c(-1,10,50,100,Inf),labels=bands))
shade_matrix <- rbind(c('#D1837C','#BD5D55','#9C3D36','#702721'),c('#E2AE65','#CD8D39','#A96920','#79450D'),c('#8C9FAF','#687F93','#476279','#293F55'),c('#E0E3E7','#B8BEC6','#8C949E','#5F6873'))
keys <- expand.grid(band_index=1:4,priority_level=1:4)
keys$count_band <- bands[keys$band_index]
keys$priority_tier <- paste('Level',keys$priority_level)
keys$fill <- shade_matrix[cbind(keys$priority_level,keys$band_index)]
keys$key <- paste(keys$priority_level,keys$count_band)
grid_data$fill <- keys$fill[match(paste(grid_data$priority_level,grid_data$count_band),keys$key)]
# WCAG relative luminance chooses the stronger of black/white text contrast.
rgb <- t(grDevices::col2rgb(grid_data$fill))/255
linear <- ifelse(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)^2.4)
lum <- as.vector(linear %*% c(.2126,.7152,.0722))
grid_data$text_colour <- ifelse((lum+.05)/.05 >= 1.05/(lum+.05),'#000000','#FFFFFF')
stopifnot(nrow(grid_data)==289,sum(grid_data$compound_count)==nrow(compounds),all(pmax((lum+.05)/.05,1.05/(lum+.05))>=4.5))
# Guide thickness: 1.15 y units x 0.4 aspect = 0.46 x units on both edges.
# Complete label boundaries: retain all 17 x 17 integer cells.
boundaries <- rbind(
 data.frame(x=c(3.5,7.5,11.5),xend=c(3.5,7.5,11.5),y=-.5,yend=16.5),
 data.frame(x=-.5,xend=16.5,y=c(3.5,7.5,11.5),yend=c(3.5,7.5,11.5)))
guides <- data.frame(label=c('L','M','H','vH'),lo=c(-.5,3.5,7.5,11.5),hi=c(3.5,7.5,11.5,16.5),fill=c('#AEB7C2','#36495D','#C88736','#A9463E'))
guides$text_colour <- c('#202830','white','#202830','white')
guides$mid <- (guides$lo+guides$hi)/2
heatmap_plot <- function(compact=FALSE) {
 p <- ggplot(grid_data,aes(Hazard_score,Exposure_score))+
 geom_tile(aes(fill=fill),colour='white',linewidth=.15)+scale_fill_identity()+
 geom_segment(data=boundaries,aes(x=x,y=y,xend=xend,yend=yend),inherit.aes=FALSE,linewidth=.35,linetype='dashed',colour='#202830')+
 geom_text(aes(label=compound_count,colour=text_colour),size=2.3)+scale_colour_identity()+
 geom_rect(data=guides,aes(xmin=lo,xmax=hi,ymin=16.75,ymax=17.9,fill=fill),inherit.aes=FALSE,colour='white',linewidth=.3)+
 geom_text(data=guides,aes(x=mid,y=17.325,label=label,colour=text_colour),inherit.aes=FALSE,size=2.6,fontface='bold')+
 geom_rect(data=guides,aes(ymin=lo,ymax=hi,xmin=16.75,xmax=17.21,fill=fill),inherit.aes=FALSE,colour='white',linewidth=.3)+
 geom_text(data=guides,aes(y=mid,x=16.98,label=label,colour=text_colour),inherit.aes=FALSE,size=2.6,fontface='bold')+
 scale_x_continuous(breaks=0:16,expand=c(0,0))+scale_y_continuous(breaks=0:16,expand=c(0,0))+
 coord_fixed(ratio=.4,xlim=c(-.5,17.3),ylim=c(-.5,18),clip='off')+
 labs(x='Hazard score (rounded)',y='Exposure score (rounded)')+
 priority_landscape_theme(8)+theme(axis.line=element_blank(),axis.ticks=element_blank(),plot.margin=margin(4,5,4,5))
 keys$priority_tier <- factor(keys$priority_tier,levels=priority_levels)
 # Keep all four count bands explicit; vertically stack four short colour bars.
 key <- ggplot(keys,aes(band_index,5-priority_level))+
 geom_tile(aes(fill=fill),height=.18,width=1)+scale_fill_identity()+
 geom_text(aes(y=5-priority_level+.25,label=count_band),size=1.9,colour='#30343A')+
 annotate('text',x=2.5,y=(4:1)-.26,label=priority_levels,size=2.7,colour='#202830')+
 scale_x_continuous(limits=c(.4,4.6),expand=c(0,0))+
 scale_y_continuous(limits=c(.4,4.65),expand=c(0,0))+
 labs(title='Priority level',subtitle='Compounds per cell')+
 theme_void(base_size=8,base_family=resolve_manuscript_font())+
 theme(plot.title=element_text(size=8,hjust=.5),plot.subtitle=element_text(size=6.5,hjust=.5),plot.margin=margin(7,5,9,7))
 p+key+plot_layout(widths=c(4.7,1.3))

}
assemble_preview_v3 <- function(plots,config) {
 inset <- config$layout$inset
 top <- tag_priority_panel(plots$priority_score_distribution,'a',config)+
 inset_element(plots$regulatory_context_inset,left=inset$left,bottom=inset$bottom,right=inset$right,top=inset$top,align_to=inset$align_to,clip=FALSE)
 middle <- grid::grobTree(patchworkGrob(plots$hazard_exposure_landscape),
 grid::textGrob('b',x=grid::unit(.006,'npc'),y=grid::unit(.994,'npc'),just=c('left','top'),gp=grid::gpar(fontfamily=resolve_manuscript_font(),fontsize=8.5,fontface='bold')))
 bottom <- tag_priority_panel(plots$hazard_component_profiles,'c',config)+
 tag_priority_panel(plots$exposure_component_profiles,'d',config)+plot_layout(widths=c(1,1))
 wrap_elements(full=top)/wrap_elements(full=middle)/wrap_elements(full=bottom)+plot_layout(heights=config$layout$row_heights)
}
save_tables(list(heatmap_source_data=grid_data,colour_key=keys,region_boundaries=boundaries,label_guides=guides),'hazard_exposure_landscape')
save_tables(list(compound_values=compounds[,c('inchikey','Hazard_score_raw','Exposure_score_raw','Hazard_score','Exposure_score','Priority_score','Priority_level','Hazard_label','Exposure_label')]))
plots <- lapply(ids,function(id) get(paste0('plot_',id))(prepared[[id]]$source_data,config,'publication'));names(plots)<-ids
# Numeric labels here refer to raw component scores, not priority classes.
profile_labels <- function(x) {x[x=='Low (0.5)']<-'Score 0.5';x[x=='Moderate (1)']<-'Score 1';x[x=='High (2)']<-'Score 2';x}
for(id in c('hazard_component_profiles','exposure_component_profiles')) {
 s <- plots[[id]]$scales$get_scales('fill');s$labels <- profile_labels
 plots[[id]] <- plots[[id]]+labs(subtitle='Unweighted component scores')
}
plots$hazard_exposure_landscape <- heatmap_plot(TRUE)
export_figure(assemble_preview_v3(plots,config),file.path(output_dir,'Fig3'),183,218,dpi=600)
export_figure(heatmap_plot(FALSE),file.path(output_dir,'Fig3b'),260,110,dpi=600)
files <- list.files(data_dir,recursive=TRUE,full.names=TRUE,pattern='\\.csv$')
write_json_utf8(list(status='preview; formal figure lock unchanged',source=input,source_sha256=sha256_file(input),policy='output/2026-10-27/scoring_config.json',policy_sha256=sha256_file('output/2026-10-27/scoring_config.json'),script_sha256=sha256_file('Figure/Fig3/preview_level4_v3.R'),population=nrow(compounds),level_counts=as.list(table(compounds$Priority_tier)),heatmap_cells=nrow(grid_data),palette=config$priority_palette,tables=as.list(setNames(vapply(files,sha256_file,character(1)),files))),file.path(data_dir,'preview_manifest.json'))
