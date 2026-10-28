#!/usr/bin/env Rscript
# SI evidence grid: every five-level Level 1 compound, existing scores/ranks.
# R-only figure drawing; Arial, 260 x 225 mm, editable cairo_pdf and 600 dpi PNG.
# No scoring changes, omitted records, inference or count-dependent shading.
suppressPackageStartupMessages(library(grid))
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2)
payload <- jsonlite::fromJSON(args[[1]],simplifyVector=TRUE)
out <- args[[2]]
font <- 'Arial'; ink <- '#263440'; muted <- '#69747D'; teal <- '#326F78'; warm <- '#9D5149'
cohort <- payload$rows
components <- payload$components
score_fill <- unlist(payload$score_palette)
stopifnot(nrow(cohort)==payload$metadata$cohort_size,capabilities('cairo'))
tx <- function(label,x,y,size=7.2,col=ink,face='plain',just='left') {
 grid.text(label,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,col=col,fontface=face,lineheight=1.0))
}
rect <- function(x,y,w,h,fill,col=NA,lwd=.3) grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),gp=gpar(fill=fill,col=col,lwd=lwd))
line <- function(x1,y1,x2,y2,col='#DBE1E5',lwd=.45) grid.lines(x=unit(c(x1,x2),'mm'),y=unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
wrap_measured <- function(text,width_mm,size) {
 chars <- strsplit(text,'',fixed=TRUE)[[1]]
 lines <- character(); current <- '';last_break <- 0L
 textwidth <- function(z) convertWidth(grobWidth(textGrob(z,gp=gpar(fontfamily=font,fontsize=size))), 'mm',valueOnly=TRUE)
 for(ch in chars) {
  next_line <- paste0(current,ch)
  if(nzchar(current) && textwidth(next_line)>width_mm) {
   spaces <- gregexpr('[ ,;-]',current)[[1]];br <- tail(spaces[spaces>0],1)
   if(length(br) && br>nchar(current)*.5) {
    end <- if(substr(current,br,br)==' ') br-1 else br
    lines <- c(lines,substr(current,1,end)); current <- paste0(substr(current,br+1,nchar(current)),ch)
   } else {lines <- c(lines,current);current <- ch}
  } else current <- next_line
 }
 paste(c(lines,current),collapse='\n')
}

# Measure on the final vector device; paginate according to actual wrapped text.
grDevices::cairo_pdf(file.path(out,'SILevel1Evidence.pdf'),width=260/25.4,height=225/25.4,family=font)
cohort$name_wrapped <- vapply(cohort$Name,wrap_measured,character(1),width_mm=67,size=7.4)
cohort$use_wrapped <- vapply(cohort$primary_use_display,wrap_measured,character(1),width_mm=32,size=6.9)
lines_in <- function(z) length(strsplit(z,'\n')[[1]])
row_heights <- pmax(5.35,2.7*pmax(vapply(cohort$name_wrapped,lines_in,integer(1)),vapply(cohort$use_wrapped,lines_in,integer(1))))
page_height <- 183.5
stopifnot(all(row_heights<=page_height))
pages <- list();current <- integer();used <- 0
for(i in seq_len(nrow(cohort))) {
 if(length(current) && (used+row_heights[i]>page_height+1e-8 || length(current)>=34L)) {
  pages[[length(pages)+1L]] <- current;current <- integer();used <- 0
 }
 current <- c(current,i);used <- used+row_heights[i]
}
if(length(current)) pages[[length(pages)+1L]] <- current
component_x <- c(184,189,194,199,207,212,217,222,227,232)
draw_evidence <- function(page,newpage=TRUE) {
 if(newpage) grid.newpage()
 pushViewport(viewport(x=unit(0,'mm'),y=unit(-16,'mm'),width=unit(260,'mm'),height=unit(225,'mm'),just=c('left','bottom')))
 tx(sprintf('%d / %d',page,length(pages)),251,238,7,just='right',col=muted)
 tx('IDENTITY AND PRIMARY USE',9,234,7.1,col=muted,face='bold')
 tx('EXISTING SCORES',153.5,234,7.1,col=muted,face='bold',just='centre')
 tx('HAZARD',191.5,234,7.1,col=warm,face='bold',just='centre')
 tx('EXPOSURE',219.5,234,7.1,col=teal,face='bold',just='centre')
 tx('GIC',245,234,7.1,col=muted,face='bold',just='centre')
 tx('ID',9,227,7,face='bold');tx('Compound',21,227,7,face='bold');tx('CAS',91,227,7,face='bold');tx('Primary use',115,227,7,face='bold')
 for(j in 1:4) tx(c('H','E','Total','Rank')[j],c(152,159,167,176)[j],227,7,face='bold',just='centre')
 for(j in seq_along(component_x)) {
  tx(components$abbreviation[j],component_x[j],227,6.6,face='bold',just='centre')
  tx(paste0('x',components$weight[j]),component_x[j],222.8,6.1,col=muted,just='centre')
 }
 tx('Code',245,227,6.8,face='bold',just='centre');line(9,220,251,220,col=ink,lwd=.6)
 used <- 0
 for(index in pages[[page]]) {
  s <- cohort[index,,drop=FALSE];rh <- row_heights[index];y <- 219.275-used-rh/2
  if(index %% 2L==0L) rect(130,y,242,rh,'#F7F9FA')
  tx(s$Display_ID,9,y,6.8,col=muted);tx(s$name_wrapped,21,y,7.4)
  tx(s$CAS,91,y,7.1,col=muted);tx(s$use_wrapped,115,y,6.9)
  rect(152,y,5.6,4.15,'#F2E4E1');rect(159,y,5.6,4.15,'#E5EFF0')
  tx(s$Hazard_score,152,y,7.2,col=warm,face='bold',just='centre')
  tx(s$Exposure_score,159,y,7.2,col=teal,face='bold',just='centre')
  tx(s$Priority_score,167,y,7.3,face='bold',just='centre');tx(s$Priority_rank,176,y,6.8,col=muted,just='centre')
  for(j in seq_along(component_x)) {
   v <- s[[components$field[j]]]
   fill <- if(is.na(v)) '#E3E6E9' else score_fill[as.character(v)]
   rect(component_x[j],y,4.3,4.15,fill,col='#D1DCDD')
   tx(if(is.na(v)) 'NA' else as.character(v),component_x[j],y,6.1,col=if(!is.na(v)&&v==2) 'white' else ink,just='centre')
  }
  rect(245,y,5.3,4.15,s$Regulatory_colour)
  tx(s$Regulatory_code,245,y,6.8,col=if(s$Regulatory_code %in% c('A','B')) 'white' else ink,face='bold',just='centre')
  used <- used+rh
 }
 line(9,34,251,34);tx('Component tiles: unweighted scores',9,29,7.2,face='bold')
 for(j in seq_along(score_fill)) {x <- 69+(j-1)*13;rect(x,29,4,3.8,score_fill[j],col='#C5D2D4');tx(names(score_fill)[j],x+3,29,6.7)}
 rect(136,29,4,3.8,'#E3E6E9',col='#B8C0C6');tx('NA = missing',139,29,6.7)
 popViewport()
}
tryCatch(for(page in seq_along(pages)) draw_evidence(page,newpage=page!=1L),finally=grDevices::dev.off())
# All page renders are temporary QA; only the combined PDF is delivered.
qa_dir <- file.path(out,'.qa');dir.create(qa_dir,showWarnings=FALSE)
svglite::svglite(file.path(qa_dir,'figure_page1.svg'),width=260/25.4,height=225/25.4)
tryCatch(draw_evidence(1L),finally=grDevices::dev.off())
for(page in seq_along(pages)) {
 destination <- if(page==1L) file.path(out,'SILevel1Evidence.png') else file.path(qa_dir,paste0('figure_page',page,'.png'))
 ragg::agg_png(destination,width=260,height=225,units='mm',res=600,background='white')
 tryCatch(draw_evidence(page),finally=grDevices::dev.off())
}
jsonlite::write_json(list(pages=length(pages),rows_per_page=vapply(pages,length,integer(1)),rows=nrow(cohort),font=font,min_font_pt=6.1,width_mm=260,height_mm=225,dpi=600),file.path(out,'figure_qa.json'),auto_unbox=TRUE,pretty=TRUE)
