#!/usr/bin/env Rscript
# Nested use treemap: 101 equal-area chemical tiles, full names, structure strips.
# Header-aware layout keeps the data tile area equal; group headers/gutters are
# non-data space. R/grid only, Arial 11.5 pt names, editable PDF/SVG, 600 dpi PNG.
# width_mm = 540, height_mm = 430: full-name review proof.
suppressPackageStartupMessages(library(grid))
root<-'/Users/ruiwang/Projects/APPs/PlastPrior'
module<-file.path(root,'Figure/Level1UseTreemap')
out<-file.path(module,'output')
data_out<-file.path(root,'output/figure_data/Level1UseTreemap/review')
input<-file.path(root,'output/figure_data/Level1Identity/review/compound_identity.csv')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source(file.path(root,'Figure/_shared/theme.R'))
font<-resolve_manuscript_font()
sha<-function(p) digest::digest(file=p,algo='sha256',serialize=FALSE)
protected<-unlist(lapply(c('Level1Identity','Level1IdentityTree','Level1UseMatrix'),function(m)
 list.files(file.path(root,'Figure',m,'output'),full.names=TRUE)))
before<-setNames(vapply(c(input,protected),sha,character(1)),c(input,protected))
d<-read.csv(input,stringsAsFactors=FALSE,check.names=FALSE)
classification<-jsonlite::fromJSON(file.path(root,'output/figure_data/Level1Identity/review/classification.json'))
for(p in names(classification$source_hashes)) stopifnot(sha(file.path(root,p))==classification$source_hashes[[p]])
full<-readr::read_csv(file.path(root,'output/2026-10-27/PlastPrior_results.csv'),show_col_types=FALSE)
idx<-match(d$inchikey,full$inchikey)
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),!anyNA(idx),all(d$Figure_priority_level==1))
for(f in c('Name','CAS','SMILES','Hazard_score','Exposure_score','Priority_score','Priority_rank'))
 stopifnot(identical(as.character(d[[f]]),as.character(full[[f]][idx])))
groups<-c('hal_non_aromatic','hal_aromatic_chx','hal_aromatic_o','hal_aromatic_ns','hal_heterocycle',
 'nonhal_aromatic_ch','nonhal_o','nonhal_heterocycle','nonhal_other')
colours<-setNames(c('#3A7582','#687FA9','#947BAC','#AA8650','#A45F62','#658B66','#B18B60','#8C7E71','#73848F'),groups)
codes<-setNames(LETTERS[1:9],groups)
uses<-as.data.frame(table(d$primary_use),stringsAsFactors=FALSE);names(uses)<-c('primary_use','n')
uses<-uses[order(-uses$n,uses$primary_use,method='radix'),];rownames(uses)<-NULL
stopifnot(nrow(uses)==16,sum(uses$n)==101)
width_mm<-540;height_mm<-430
name_pt<-11.5;header_pt<-12
margin<-9;map_bottom<-65;map_width<-width_mm-2*margin;map_height<-height_mm-map_bottom-margin
pad<-2.5;header_h<-18;cell_pad<-2.2;strip_h<-1.25
ink<-'#26343D';muted<-'#6B7882'
metric_width<-function(s,size,bold=FALSE) convertWidth(grobWidth(textGrob(s,
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold) 'bold' else 'plain'))),'mm',valueOnly=TRUE)
wrap<-function(s,w,size,bold=FALSE) {
 chars<-strsplit(s,'',fixed=TRUE)[[1]];result<-character();current<-''
 for(ch in chars) {
  if(nzchar(current)&&metric_width(paste0(current,ch),size,bold)>w) {
   br<-gregexpr('[ ,;-]',current)[[1]];br<-tail(br[br>0],1)
   if(length(br)&&br>nchar(current)*.2) {
    end<-if(substr(current,br,br)==' ') br-1 else br
    result<-c(result,substr(current,1,end));current<-paste0(substr(current,br+1,nchar(current)),ch)
   } else {result<-c(result,current);current<-ch}
  } else current<-paste0(current,ch)
 }
 result<-c(result,current)
 # Avoid isolated one-letter suffixes caused by hard wrapping chemical names.
 if(length(result)>1) for(k in seq.int(length(result),2)) {
  if(nchar(result[k])<5&&!grepl('[ ,;-]$',result[k-1])&&nchar(result[k-1])>7) {
   n<-min(5-nchar(result[k]),nchar(result[k-1])-5)
   proposed<-paste0(substr(result[k-1],nchar(result[k-1])-n+1,nchar(result[k-1])),result[k])
   if(metric_width(proposed,size,bold)<=w) {
    result[k-1]<-substr(result[k-1],1,nchar(result[k-1])-n);result[k]<-proposed
   }
  }
 }
 result
}
text_height<-function(lines,size,bold=FALSE) convertHeight(grobHeight(textGrob(paste(lines,collapse='\n'),
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold) 'bold' else 'plain',lineheight=1.05))),'mm',valueOnly=TRUE)

# Fixed balanced binary topology avoids unstable group reordering during fitting.
make_tree<-function(ids,w,h) {
 if(length(ids)==1) return(list(ids=ids))
 weights<-uses$n[ids];split<-which.min(abs(cumsum(weights)[-length(ids)]-sum(weights)/2))
 a<-ids[seq_len(split)];b<-ids[-seq_len(split)];fraction<-sum(uses$n[a])/sum(weights)
 vertical<-w>=h
 if(length(ids)==2&&min(ids)>=6) vertical<-FALSE
 list(ids=ids,vertical=vertical,
      a=make_tree(a,if(vertical) w*fraction else w,if(vertical) h else h*fraction),
      b=make_tree(b,if(vertical) w*(1-fraction) else w,if(vertical) h else h*(1-fraction)))
}
topology<-make_tree(seq_len(nrow(uses)),map_width,map_height)
rectangles<-function(tree,weights,x,y,w,h) {
 if(length(tree$ids)==1) return(data.frame(id=tree$ids,x=x,y=y,w=w,h=h))
 fraction<-sum(weights[tree$a$ids])/sum(weights[tree$ids])
 if(tree$vertical) rbind(rectangles(tree$a,weights,x,y,w*fraction,h),
                         rectangles(tree$b,weights,x+w*fraction,y,w*(1-fraction),h))
 else rbind(rectangles(tree$a,weights,x,y+h*(1-fraction),w,h*fraction),
            rectangles(tree$b,weights,x,y,w,h*(1-fraction)))
}
# Solve group outer areas so their inner data areas are exactly n * one tile area.
weights<-uses$n/sum(uses$n)*map_width*map_height
for(iteration in 1:2000) {
 regions<-rectangles(topology,weights,margin,map_bottom,map_width,map_height)
 regions<-regions[order(regions$id),]
 inner_area<-(regions$w-2*pad)*(regions$h-header_h-2*pad)
 stopifnot(all(inner_area>0))
 unit_area<-sum(inner_area)/101
 error<-uses$n*unit_area-inner_area
 if(max(abs(error)/uses$n)<1e-7) break
 weights<-weights+.65*error
 stopifnot(all(weights>0))
}
stopifnot(iteration<2000,max(abs(inner_area/uses$n-unit_area))<1e-6)

invisible(ragg::agg_capture(width=1600,height=1200,res=300))
tiles<-list();prepared<-list();header_labels<-list();tile_count<-0L
for(i in seq_len(nrow(uses))) {
 region<-regions[i,];s<-d[d$primary_use==uses$primary_use[i],]
 s<-s[order(match(s$structure_group,groups),tolower(s$Name),s$inchikey,method='radix'),]
 inner_w<-region$w-2*pad;inner_h<-region$h-header_h-2*pad
 header_lines<-wrap(uses$primary_use[i],inner_w-13,header_pt,TRUE)
 stopifnot(text_height(header_lines,header_pt,TRUE)<=header_h-2)
 header_labels[[i]]<-header_lines
 # Equal-area rows, choosing their number for readable full names and aspect ratio.
 candidates<-list()
 for(nrows in seq_len(nrow(s))) {
  counts<-rep(nrow(s)%/%nrows,nrows);counts[seq_len(nrow(s)%%nrows)]<-counts[seq_len(nrow(s)%%nrows)]+1L
  cursor<-1L;y_top<-region$y+pad+inner_h;parts<-list();overflow<-0;worst_aspect<-1
  for(nc in counts) {
   tw<-inner_w/nc;th<-nc*unit_area/inner_w
   if(tw<=2*cell_pad+2||th<=2*cell_pad+strip_h) {overflow<-Inf;break}
   for(col in seq_len(nc)) {
    ls<-wrap(s$Name[cursor],tw-2*cell_pad,name_pt)
    required<-text_height(ls,name_pt)
    available<-th-2*cell_pad-strip_h
    overflow<-max(overflow,required-available)
    worst_aspect<-max(worst_aspect,(tw/th)/2.8,2.8/(tw/th))
    parts[[cursor]]<-list(row=s[cursor,],x=region$x+pad+(col-1)*tw,y=y_top-th,w=tw,h=th,lines=ls,
                         text_height=required,available_height=available)
    cursor<-cursor+1L
   }
   y_top<-y_top-th
  }
  if(is.finite(overflow)&&overflow<=0) candidates[[length(candidates)+1]]<-list(parts=parts,score=worst_aspect)
 }
 if(!length(candidates)) stop('Full names do not fit at fixed font size in group: ',uses$primary_use[i])
 best<-candidates[[which.min(vapply(candidates,function(x)x$score,numeric(1)))]]
 prepared[[i]]<-best$parts
 for(t in best$parts) {
  tile_count<-tile_count+1L
  tiles[[tile_count]]<-data.frame(record_id=t$row$record_id,inchikey=t$row$inchikey,Name=t$row$Name,
    primary_use=t$row$primary_use,structure_group=t$row$structure_group,structure_code=codes[t$row$structure_group],
    x_mm=t$x,y_mm=t$y,width_mm=t$w,height_mm=t$h,area_mm2=t$w*t$h,
    font_pt=name_pt,name_lines=length(t$lines),text_height_mm=t$text_height,available_height_mm=t$available_height)
 }
}
grDevices::dev.off()
tile_data<-do.call(rbind,tiles)
stopifnot(nrow(tile_data)==101,!anyDuplicated(tile_data$inchikey),setequal(tile_data$inchikey,d$inchikey),
          max(tile_data$area_mm2)-min(tile_data$area_mm2)<1e-6)
regions$primary_use<-uses$primary_use;regions$compound_count<-uses$n
regions$header_height_mm<-header_h;regions$padding_mm<-pad
readr::write_csv(tile_data,file.path(data_out,'compound_tiles.csv'))
readr::write_csv(regions,file.path(data_out,'use_regions.csv'))
readr::write_csv(d,file.path(data_out,'compound_membership.csv'))
class_key<-data.frame(code=unname(codes),structure_group=groups,
 label=unname(unlist(classification$group_labels[groups])),colour=unname(colours))
readr::write_csv(class_key,file.path(data_out,'structure_key.csv'))
txt<-function(s,x,y,size=11.5,col=ink,just='left',bold=FALSE) {
 grid.text(s,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,col=col,fontface=if(bold) 'bold' else 'plain',lineheight=1.05))
}
rect<-function(x,y,w,h,fill,col=NA,lwd=.4) grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),
 just=c('left','bottom'),gp=gpar(fill=fill,col=col,lwd=lwd))
draw<-function() {
 grid.newpage()
 for(i in seq_len(nrow(uses))) {
  region<-regions[i,]
  rect(region$x+.55,region$y+.55,region$w-1.1,region$h-1.1,'#F0F3F5',col='#D4DDE2',lwd=.6)
  hy<-region$y+region$h-pad-header_h/2
  txt(paste(header_labels[[i]],collapse='\n'),region$x+pad+1,hy,header_pt,bold=TRUE)
  txt(uses$n[i],region$x+region$w-pad-1,hy,12,col=muted,just='right',bold=TRUE)
  for(t in prepared[[i]]) {
   rect(t$x,t$y,t$w,t$h,'white',col='#D6DFE3',lwd=.5)
   rect(t$x+.35,t$y+t$h-strip_h-.35,t$w-.7,strip_h,colours[t$row$structure_group])
   y<-t$y+(t$h-strip_h)/2
   txt(paste(t$lines,collapse='\n'),t$x+cell_pad,y,name_pt)
  }
 }
 # Shared colour-strip key; the only annotations outside the nested rectangles.
 for(j in seq_along(groups)) {
  col<-(j-1)%%3;row<-(j-1)%/%3;x<-margin+col*(map_width/3);y<-48-row*15
  rect(x,y-1.3,6,2.6,colours[j])
  txt(paste0(codes[j],'  ',class_key$label[j]),x+9,y,10.5)
 }
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_use_treemap.',fmt))
 if(fmt=='pdf') grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg') svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png') ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(names(before),sha,character(1)),names(before))))
writeLines(c('Primary uses and structural classes of the 101 Level 1 compounds.',
 'Each white data rectangle represents one compound and retains its full original name. The 101 data rectangles have equal area. The 16 outer regions group compounds by their user-supplied primary use, with the compound count beside each heading. Within each use, compounds are ordered by structural class then alphabetically, without modifying the original rank field. A coloured strip identifies the same structural class A-I as the existing classification tree.',
 'Data tile area represents one compound, not score, risk, production volume or certainty. The sum of white data rectangle areas in each use group is exactly proportional to its compound count. Outer region footprints additionally include titles and gutters; those non-data areas should not be interpreted quantitatively. No compound is omitted or duplicated. Primary uses are general-use annotations and are not asserted to be functions within plastics.',
 'This layout preserves five-level Level 1 membership and all existing scores and ranks. The original list, classification tree and bubble matrix remain unchanged. Structural classification rules are retained in the existing source-data classification report.',
 sprintf('Review size %.0f x %.0f mm; all compound names %.1f pt, use headings %.0f pt, structure key 10.5 pt. Long names wrap without truncation. Final journal formatting requires reflow rather than uniform reduction.',width_mm,height_mm,name_pt,header_pt)),file.path(module,'captions.txt'))
files<-list.files(out,full.names=TRUE);files<-files[basename(files)!='manifest.json']
manifest<-list(status='review',backend='R',width_mm=width_mm,height_mm=height_mm,name_font_pt=name_pt,
 use_header_font_pt=header_pt,cohort=101,use_groups=16,structural_groups=9,
 data_tile_area_mm2=unit_area,tile_area_range_mm2=range(tile_data$area_mm2),
 max_name_lines=max(tile_data$name_lines),minimum_text_clearance_mm=min(tile_data$available_height_mm-tile_data$text_height_mm),
 header_area_solver_iterations=iteration,all_names_complete=TRUE,excluded_compounds=0,
 scores_ranks_unchanged=TRUE,previous_figures_unchanged=TRUE,source_hashes=classification$source_hashes,
 protected_hashes=as.list(before),script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(files,sha,character(1)),basename(files))),
 source_data_hashes=as.list(setNames(vapply(list.files(data_out,full.names=TRUE),sha,character(1)),list.files(data_out))),
 qa_notes=c('R parse checked by execution; 540 mm full-name review width explicitly selected',
 'Equal compound data areas; parent headers and gutters are not quantitative',
 '11.5 pt compound names; editable PDF/SVG and 600 dpi PNG; TIFF not requested'))
jsonlite::write_json(manifest,file.path(out,'manifest.json'),pretty=TRUE,auto_unbox=TRUE)
cat(sprintf('Rendered 101 equal-area compound tiles in 16 use regions; %.1f pt names.\n',name_pt))
