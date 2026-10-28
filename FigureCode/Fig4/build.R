#!/usr/bin/env Rscript
source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
load_plot_data()
width_mm <- 320; height_mm <- 245
ink <- '#26343D'; tick_col <- '#5A6670'
text <- function(s,x,y,size=11.5,bold=FALSE,just='left',colour=ink) {
 grid.text(s,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold)'bold' else 'plain',col=colour,lineheight=.98))
}
line <- function(x1,y1,x2,y2,col=ink,lwd=.6) grid.lines(unit(c(x1,x2),'mm'),unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
bar_panel <- function(tbl,tag,title,left,title_y,x0,w,ys,axis_y,xmax,ticks,colour) {
 text(tag,left,title_y,14,TRUE)
 text(title,left+7,title_y,13.5,TRUE)
 for(j in seq_len(nrow(tbl))) {
  text(tbl$label[j],x0-3,ys[j],11.5,just='right')
  grid.rect(x=unit(x0,'mm'),y=unit(ys[j],'mm'),width=unit(w*tbl$n[j]/xmax,'mm'),height=unit(6,'mm'),
   just=c('left','centre'),gp=gpar(fill=colour,col=NA))
  text(tbl$n[j],x0+w*tbl$n[j]/xmax+2,ys[j],11.5)
 }
 line(x0,axis_y,x0+w,axis_y)
 for(t in ticks) {
  xx<-x0+w*t/xmax
  line(xx,axis_y,xx,axis_y-1.3)
  text(t,xx,axis_y-4,10.5,just='centre',colour=tick_col)
 }
 text('Number of compounds',x0+w/2,axis_y-11,11.5,just='centre')
}
draw <- function() {
 grid.newpage()
 bar_panel(use,'a','Primary uses',6,234,77,67,seq(217,32,length.out=16),22,30,c(0,10,20,30),'#347681')
 bar_panel(structure,'b','Structural classes',163,234,239,68,seq(217,125,length.out=9),115,35,c(0,10,20,30),'#687FA9')
 bar_panel(reg,'c','GIC regulatory annotations',163,95,239,68,seq(80,32,length.out=5),22,50,c(0,10,20,30,40,50),'#786086')
}
for(fmt in c('pdf','png')) {
 p <- file.path(output_dir,paste0('Fig4.',fmt))
 if(fmt=='pdf') grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
