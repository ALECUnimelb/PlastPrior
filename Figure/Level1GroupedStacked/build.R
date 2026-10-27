#!/usr/bin/env Rscript
# Two columns, 40 observed use-structure bars, 59 regulatory count segments.
# Review width_mm = 360, height_mm = 372; Arial labels at 11.5 pt.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root,'Figure/Level1GroupedStacked')
out <- file.path(module,'output')
data_out <- file.path(root,'output/figure_data/Level1GroupedStacked/review')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source_dir <- file.path(root,'output/figure_data/Level1Composition/review')
read <- function(p)as.data.frame(readr::read_csv(p,show_col_types=FALSE))
sha <- function(p)digest::digest(file=p,algo='sha256',serialize=FALSE)
old_modules <- c('Level1Evidence','Level1Identity','Level1IdentityTree','Level1UseMatrix',
 'Level1UseTreemap','Level1Composition','Level1Alluvial')
protected <- c(list.files(source_dir,full.names=TRUE),file.path(root,'output/2026-10-27/PlastPrior_results.csv'),
 unlist(lapply(old_modules,function(m)list.files(file.path(root,'Figure',m,'output'),full.names=TRUE))))
before <- setNames(vapply(protected,sha,character(1)),protected)
d <- read(file.path(source_dir,'compound_membership.csv'))
full <- read(file.path(root,'output/2026-10-27/PlastPrior_results.csv'))
idx <- match(d$inchikey,full$inchikey)
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),!anyNA(idx),all(d$Figure_priority_level==1),
 setequal(d$inchikey,full$inchikey[full$Hazard_score>=12 & full$Exposure_score>=12]))
for(f in c('Name','CAS','SMILES','Hazard_score','Exposure_score','Priority_score','Priority_rank','Top_n_selected','GIC_regulatory_status'))
 stopifnot(identical(as.character(d[[f]]),as.character(full[[f]][idx])))
u <- read(file.path(source_dir,'use_counts.csv'))
s <- read(file.path(source_dir,'structure_counts.csv'))
r <- read(file.path(source_dir,'reg_counts.csv'))
u <- u[order(-u$n,u$category,method='radix'),]
u$heading <- gsub('\n',' ',u$label,fixed=TRUE)
colours <- setNames(c('#A7655E','#BD9451','#87739E','#648F9F','#94A18A'),r$category)
segments <- aggregate(rep(1L,nrow(d)),d[,c('primary_use','structure_group','GIC_regulatory_status')],sum)
names(segments)[4] <- 'n'
bars <- aggregate(n~primary_use+structure_group,segments,sum)
bars <- bars[order(match(bars$primary_use,u$category),match(bars$structure_group,s$category)),]
bars$bar_id <- sprintf('B%02d',seq_len(nrow(bars)))
bars$label <- s$label[match(bars$structure_group,s$category)]
u$bar_count <- as.integer(table(factor(bars$primary_use,levels=u$category)))
stopifnot(nrow(bars)==40L,nrow(segments)==59L,sum(bars$n)==101L,sum(segments$n)==101L,
 sum(u$bar_count)==40L,nrow(u)==16L,nrow(s)==9L,nrow(r)==5L)

width_mm<-360;height_mm<-372;font<-'Arial';ink<-'#26343D'
row_h<-9.5;header_h<-10;min_gap<-3
group_h<-header_h+u$bar_count*row_h
# Eight intact groups per column. Balance actual group heights first, then
# compound counts. The two largest uses start separate columns. Enumerating
# 3,432 partitions is deterministic and changes only the display arrangement.
candidates<-lapply(combn(3:nrow(u),7,simplify=FALSE),function(z)c(1L,z))
costs<-t(vapply(candidates,function(ix)c(
 abs(2*sum(group_h[ix])-sum(group_h)),abs(2*sum(u$n[ix])-sum(u$n))),numeric(2)))
chosen<-candidates[[order(costs[,1],costs[,2],seq_along(candidates))[1]]]
u$column<-ifelse(seq_len(nrow(u))%in%chosen,1L,2L)
base_heights<-sapply(1:2,function(col){ix<-which(u$column==col);sum(group_h[ix])+min_gap*(length(ix)-1)})
body_h<-max(base_heights);body_top<-height_mm-10;body_bottom<-body_top-body_h
stopifnot(body_bottom>70)
u$heading_y<-u$bottom_y<-NA_real_
bars$column<-bars$y_mm<-NA_real_
for(col in 1:2) {
 ix<-which(u$column==col)
 gap<-if(length(ix)>1)(body_h-sum(group_h[ix]))/(length(ix)-1) else 0
 stopifnot(gap>=min_gap-1e-8)
 y<-body_top
 for(i in ix) {
  u$heading_y[i]<-y-3.5
  j<-which(bars$primary_use==u$category[i])
  bars$column[j]<-col
  bars$y_mm[j]<-y-header_h-row_h*(seq_along(j)-.5)
  u$bottom_y[i]<-y-group_h[i]
  y<-u$bottom_y[i]-gap
 }
}
x_starts<-c(8,188);bar_offset<-73;bar_width<-80;x_max<-10
bars$x0_mm<-x_starts[bars$column]+bar_offset
segments$bar_id<-bars$bar_id[match(paste(segments$primary_use,segments$structure_group),paste(bars$primary_use,bars$structure_group))]
segments<-segments[order(match(segments$bar_id,bars$bar_id),match(segments$GIC_regulatory_status,r$category)),]
segments$x_left_mm<-segments$x_right_mm<-segments$y_mm<-NA_real_
for(i in seq_len(nrow(bars))) {
 j<-which(segments$bar_id==bars$bar_id[i]);running<-cumsum(segments$n[j])
 segments$x_left_mm[j]<-bars$x0_mm[i]+c(0,head(running,-1))*bar_width/x_max
 segments$x_right_mm[j]<-bars$x0_mm[i]+running*bar_width/x_max
 segments$y_mm[j]<-bars$y_mm[i]
 stopifnot(sum(segments$n[j])==bars$n[i])
}
segments$colour<-unname(colours[segments$GIC_regulatory_status])
stopifnot(!anyNA(segments),max(bars$n)<=x_max)

# Check actual rendered text metrics before export.
invisible(ragg::agg_capture(width=1600,height=1200,res=300))
measure<-function(z,size,bold=FALSE) {
 g<-textGrob(z,gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold)'bold' else 'plain',lineheight=.98))
 c(w=convertWidth(grobWidth(g),'mm',valueOnly=TRUE),h=convertHeight(grobHeight(g),'mm',valueOnly=TRUE))
}
label_metrics<-t(vapply(bars$label,measure,numeric(2),size=11.5))
stopifnot(all(label_metrics[,'w']<68),all(label_metrics[,'h']<row_h-.5))
heading_metrics<-t(vapply(u$heading,measure,numeric(2),size=13,bold=TRUE))
stopifnot(all(heading_metrics[,'w']<140))
grDevices::dev.off()
readr::write_csv(d,file.path(data_out,'compound_membership.csv'))
readr::write_csv(bars,file.path(data_out,'bars.csv'))
readr::write_csv(segments,file.path(data_out,'segments.csv'))
readr::write_csv(u,file.path(data_out,'use_groups.csv'))
readr::write_csv(data.frame(category=r$category,label=r$label,colour=unname(colours)),file.path(data_out,'regulatory_key.csv'))

txt<-function(z,x,y,size=11.5,bold=FALSE,just='left',col=ink)grid.text(z,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold)'bold' else 'plain',col=col,lineheight=.98))
rect<-function(x,y,w,h,fill,col=NA,lwd=.3)grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),
 just=c('left','bottom'),gp=gpar(fill=fill,col=col,lwd=lwd))
line<-function(x1,y1,x2,y2,col='#DCE2E5',lwd=.4)grid.lines(unit(c(x1,x2),'mm'),unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
luminance<-function(col) {v<-as.numeric(grDevices::col2rgb(col))/255;v<-ifelse(v<=.04045,v/12.92,((v+.055)/1.055)^2.4);sum(v*c(.2126,.7152,.0722))}
count_colour<-function(bg)if((luminance(bg)+.05)/.05>1.05/(luminance(bg)+.05))'#000000' else '#FFFFFF'
draw<-function() {
 grid.newpage()
 for(col in 1:2) {
  x0<-x_starts[col]+bar_offset
  for(t in seq(0,10,2))line(x0+bar_width*t/10,body_bottom-1,x0+bar_width*t/10,body_top-10,
   col=if(t==0)'#9BA7AE' else '#E8ECEF',lwd=if(t==0).6 else .35)
  axis_y<-body_bottom-5
  line(x0,axis_y,x0+bar_width,axis_y,col=ink,lwd=.6)
  for(t in seq(0,10,2)) {
   xx<-x0+bar_width*t/10;line(xx,axis_y,xx,axis_y-1.2,col=ink,lwd=.6)
   txt(t,xx,axis_y-4,11,just='centre')
  }
  txt('Number of compounds',x0+bar_width/2,axis_y-11,11.5,just='centre')
 }
 for(i in seq_len(nrow(u))) {
  x<-x_starts[u$column[i]]
  rect(x,u$heading_y[i]-3.6,164,7.2,'#F1F3F5')
  txt(u$heading[i],x+2,u$heading_y[i],13,TRUE)
  txt(u$n[i],x+161,u$heading_y[i],13,TRUE,just='right')
 }
 for(i in seq_len(nrow(bars)))txt(bars$label[i],bars$x0_mm[i]-3,bars$y_mm[i],11.5,just='right')
 for(i in seq_len(nrow(segments))) {
  q<-segments[i,]
  rect(q$x_left_mm,q$y_mm-3.1,q$x_right_mm-q$x_left_mm,6.2,q$colour,col='white',lwd=.45)
  txt(q$n,(q$x_left_mm+q$x_right_mm)/2,q$y_mm,10.5,just='centre',col=count_colour(q$colour))
 }
 # One shared key, matching the order of segments from left to right.
 txt('GIC regulatory annotation',8,36,11.5,TRUE)
 legend_x<-c(8,126,244,8,126);legend_y<-c(24,24,24,10,10)
 for(i in seq_len(nrow(r))) {
  rect(legend_x[i],legend_y[i]-1.5,5,3,colours[i])
  txt(r$label[i],legend_x[i]+8,legend_y[i],11)
 }
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_grouped_stacked.',fmt))
 if(fmt=='pdf')grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg')svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png')ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(protected,sha,character(1)),protected)))
writeLines(c('Structural and regulatory composition of Level 1 compounds by primary use.',
 'Each shaded heading identifies one primary use and its compound count. Each horizontal bar represents an observed use-structure combination. Its total length is the compound count; coloured segments show the counts assigned to the five GIC categories, with the count printed within each segment. Both columns use the same zero-based 0-10 axis and 8 mm per compound.',
 'All 101 unique compounds are represented once among the 40 bars and 59 nonzero regulatory segments. The 16 use groups remain intact, with eight groups and 20 bars per column. Whole groups are assigned to balance row heights and compound counts (50 left; 51 right), then ordered within each column by descending use count, with alphabetical tie-breaking. Structural categories retain the established order within each use. Zero-count use-structure combinations are not drawn; no compounds or categories are omitted.',
 'Structural categories and user-supplied primary uses retain their previous definitions. X denotes F, Cl, Br or I. GIC annotations reflect the saved source database rather than a new jurisdiction-specific legal review. The figure shows descriptive correspondence and makes no causal claim. No inferential tests or uncertainty intervals apply.',
 'Five-level Level 1 membership, original scores, ranks and Top-n flags are unchanged. Previous figures and the complete name list remain available. Review dimensions 360 x 372 mm; structure labels 11.5 pt, use headings 13 pt, segment numbers 10.5 pt. All graphics generated in R.'),file.path(module,'caption.txt'))
files<-list.files(out,full.names=TRUE);files<-files[basename(files)!='manifest.json']
jsonlite::write_json(list(status='review',backend='R',cohort=101,use_groups=16,structure_groups=9,regulatory_groups=5,
 bars=40,nonzero_segments=59,column_use_groups=as.integer(table(u$column)),column_bars=as.integer(table(bars$column)),
 width_mm=width_mm,height_mm=height_mm,label_font_pt=11.5,header_font_pt=13,segment_font_pt=10.5,
 count_axis=c(0,10),mm_per_compound=8,excluded_compounds=0,scores_ranks_unchanged=TRUE,previous_figures_unchanged=TRUE,
 minimum_label_height_clearance_mm=min(row_h-label_metrics[,'h']),
 protected_hashes=as.list(before),script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(files,sha,character(1)),basename(files))),
 qa_notes=c('Actual R execution verifies parsing; font sizes in grid helpers',
 '360 mm review width chosen to preserve large labels; final journal layout needs reflow',
 'PDF/SVG and 600 dpi PNG exported; TIFF not requested',
 'Every observed combination retained; identical count scale in both columns')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat(sprintf('Rendered %d bars and %d segments for all 101 compounds; intact use groups per column: %s.\n',
 nrow(bars),nrow(segments),paste(as.integer(table(u$column)),collapse=', ')))
