#!/usr/bin/env Rscript
source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
load_plot_data()
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
 labs(x='Hazard score',y='Exposure score')+
 priority_landscape_theme(8)+theme(axis.line=element_blank(),axis.ticks=element_blank(),plot.margin=margin(4,5,4,5))
 keys$priority_tier <- factor(keys$priority_tier,levels=priority_levels)
 # Solid swatches encode only priority level; cell counts have no colour scale.
 key <- ggplot(keys,aes(x=1,y=6-priority_level))+
 geom_tile(aes(fill=fill),height=.38,width=.34)+scale_fill_identity()+
 geom_text(aes(x=1.27,label=priority_tier),hjust=0,size=2.7,colour='#202830')+
 geom_text(aes(x=1.27,y=6-priority_level-.27,label=paste0(scales::comma(compound_count),' compounds')),hjust=0,size=2.1,colour='#505963')+
 scale_x_continuous(limits=c(.75,2.65),expand=c(0,0))+
 scale_y_continuous(limits=c(.4,5.65),expand=c(0,0))+
 labs(title='Priority level')+theme_void(base_size=8,base_family=resolve_manuscript_font())+
 theme(plot.title=element_text(size=8,hjust=.5),plot.margin=margin(7,5,9,7))
 p+key+plot_layout(widths=c(4.9,1.1))

}
plots <- lapply(ids,function(id) get(paste0('plot_',id))(prepared[[id]]$source_data,config,'publication'));names(plots)<-ids
# Numeric labels here refer to raw component scores, not priority classes.
profile_labels <- function(x) {x[x=='Low (0.5)']<-'Score 0.5';x[x=='Moderate (1)']<-'Score 1';x[x=='High (2)']<-'Score 2';x}
for(id in c('hazard_component_profiles','exposure_component_profiles')) {
 s <- plots[[id]]$scales$get_scales('fill');s$labels <- profile_labels
 plots[[id]] <- plots[[id]]+labs(subtitle='Unweighted component scores')
}
plots$hazard_exposure_landscape <- heatmap_plot(TRUE)
export_figure(assemble_priority_landscape_current(plots,config),file.path(output_dir,'Fig3'),183,218,dpi=600,formats=c('svg','pdf','png'))
# Preserve the approved plot layout's vector-device pass; keep only PNG/PDF.
unlink(file.path(output_dir,'Fig3.svg'))
