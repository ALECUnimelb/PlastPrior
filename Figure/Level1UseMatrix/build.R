#!/usr/bin/env Rscript
# Companion panel to the unchanged large-font Level 1 classification tree.
# All 101 compounds counted once by primary_use and structural display group.
# R/grid; Arial 10.2 pt row labels, editable PDF/SVG, 600 dpi PNG.
# width_mm = 260, height_mm = 260; separate review panel, not yet assembled.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root,'Figure/Level1UseMatrix')
out <- file.path(module,'output')
data_out <- file.path(root,'output/figure_data/Level1UseMatrix/review')
input <- file.path(root,'output/figure_data/Level1Identity/review/compound_identity.csv')
classification_path <- file.path(root,'output/figure_data/Level1Identity/review/classification.json')
tree_out <- file.path(root,'Figure/Level1IdentityTree/output')
tree_manifest_path <- file.path(tree_out,'manifest.json')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source(file.path(root,'Figure/_shared/theme.R'))
font <- resolve_manuscript_font()
sha <- function(p) digest::digest(file=p,algo='sha256',serialize=FALSE)
source_paths <- c(input,classification_path,tree_manifest_path)
before <- setNames(vapply(source_paths,sha,character(1)),source_paths)
tree_manifest <- jsonlite::fromJSON(tree_manifest_path)
classification <- jsonlite::fromJSON(classification_path)
stopifnot(tree_manifest$body_font_pt==11.5,tree_manifest$source_data_hash==sha(input))
for(f in names(tree_manifest$output_hashes)) stopifnot(sha(file.path(tree_out,f))==tree_manifest$output_hashes[[f]])
for(p in names(classification$source_hashes)) stopifnot(sha(file.path(root,p))==classification$source_hashes[[p]])
d <- read.csv(input,stringsAsFactors=FALSE,check.names=FALSE)
full <- readr::read_csv(file.path(root,'output/2026-10-27/PlastPrior_results.csv'),show_col_types=FALSE)
idx <- match(d$inchikey,full$inchikey)
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),!anyNA(idx),all(nzchar(d$primary_use)),
          all(d$Figure_priority_level==1),all(d$Hazard_score>=12),all(d$Exposure_score>=12))
for(f in c('Name','CAS','Hazard_score','Exposure_score','Priority_score','Priority_rank'))
 stopifnot(identical(as.character(d[[f]]),as.character(full[[f]][idx])))
groups <- c('hal_non_aromatic','hal_aromatic_chx','hal_aromatic_o','hal_aromatic_ns','hal_heterocycle',
            'nonhal_aromatic_ch','nonhal_o','nonhal_heterocycle','nonhal_other')
colours <- setNames(c('#3A7582','#687FA9','#947BAC','#AA8650','#A45F62','#658B66','#B18B60','#8C7E71','#73848F'),groups)
codes <- setNames(LETTERS[1:9],groups)
stopifnot(setequal(groups,unique(d$structure_group)))
# Verify the companion actually uses the same A-I mapping as the tree.
tree_leaves <- readr::read_csv(file.path(root,'output/figure_data/Level1IdentityTree/review/tree_leaves.csv'),show_col_types=FALSE)
stopifnot(all(tree_leaves$tree_group_code==unname(codes[tree_leaves$structure_group])))
use_counts <- as.data.frame(table(d$primary_use),stringsAsFactors=FALSE)
names(use_counts)<-c('primary_use','compound_count')
use_counts<-use_counts[order(-use_counts$compound_count,use_counts$primary_use,method='radix'),]
uses<-use_counts$primary_use
stopifnot(length(uses)==16L)
tab<-table(factor(d$primary_use,levels=uses),factor(d$structure_group,levels=groups))
stopifnot(sum(tab)==101L,identical(as.integer(rowSums(tab)),as.integer(use_counts$compound_count)),
          all(as.integer(colSums(tab))==as.integer(unlist(classification$group_counts[groups]))))
matrix_data<-as.data.frame(tab,stringsAsFactors=FALSE)
names(matrix_data)<-c('primary_use','structure_group','compound_count')
matrix_data$structure_code<-unname(codes[matrix_data$structure_group])
matrix_data$use_order<-match(matrix_data$primary_use,uses)
matrix_data$class_order<-match(matrix_data$structure_group,groups)
class_key<-data.frame(code=unname(codes),structure_group=groups,
                     label=unname(unlist(classification$group_labels[groups])),
                     colour=unname(colours),compound_count=as.integer(colSums(tab)))
readr::write_csv(matrix_data,file.path(data_out,'structure_by_primary_use.csv'))
readr::write_csv(use_counts,file.path(data_out,'primary_use_totals.csv'))
readr::write_csv(class_key,file.path(data_out,'structure_key.csv'))
readr::write_csv(d[,c('record_id','inchikey','Name','CAS','primary_use','structure_group','Hazard_score','Exposure_score','Priority_score','Priority_rank')],
                 file.path(data_out,'compound_membership.csv'))
ink<-'#26343D';muted<-'#6D7982'
width_mm<-height_mm<-260
row_size<-10.2
column_x<-108+17*(0:8)
row_y<-226-9*(0:15)
max_radius<-4.2
radius<-function(n) max_radius*sqrt(n/max(tab))
stopifnot(2*max_radius<min(abs(diff(row_y))),2*max_radius<min(diff(column_x)))
txt<-function(s,x,y,size=9,col=ink,just='left',face='plain') {
 grid.text(s,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
           gp=gpar(fontfamily=font,fontsize=size,col=col,fontface=face,lineheight=1.03))
}
stroke<-function(x1,y1,x2,y2,col='#E7ECEF',lwd=.4) grid.lines(x=unit(c(x1,x2),'mm'),y=unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
circle<-function(x,y,r,col) grid.circle(x=unit(x,'mm'),y=unit(y,'mm'),r=unit(r,'mm'),gp=gpar(fill=col,col=NA))
measure<-function(s,size) convertWidth(grobWidth(textGrob(s,gp=gpar(fontfamily=font,fontsize=size))),'mm',valueOnly=TRUE)
wrap<-function(s,w,size) {
 words<-strsplit(s,' ',fixed=TRUE)[[1]];result<-character();current<-''
 for(word in words) {
  candidate<-if(nzchar(current)) paste(current,word) else word
  if(nzchar(current)&&measure(candidate,size)>w) {result<-c(result,current);current<-word}
  else current<-candidate
 }
 paste(c(result,current),collapse='\n')
}
# Select black/white text with the higher contrast against each exact tree colour.
rgb<-t(grDevices::col2rgb(colours))/255
linear<-ifelse(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)^2.4)
lum<-as.vector(linear%*%c(.2126,.7152,.0722))
number_colours<-setNames(ifelse((lum+.05)/.05>=1.05/(lum+.05),'#000000','white'),groups)
stopifnot(all(pmax((lum+.05)/.05,1.05/(lum+.05))>=4.5))
draw<-function() {
 grid.newpage()
 txt('Structure class',176,254,11,just='centre',face='bold')
 txt('Primary use',9,244,11,face='bold')
 txt('n',96,244,10.5,just='centre',face='bold')
 for(j in 1:9) {
  txt(codes[j],column_x[j],244,12.5,col=colours[j],just='centre',face='bold')
  txt(paste0('n = ',colSums(tab)[j]),column_x[j],236.5,8.7,col=muted,just='centre')
 }
 stroke(9,232,252,232,col='#B4C1C9',lwd=.6)
 for(j in 1:9) stroke(column_x[j],230,column_x[j],86,col='#EDF0F2',lwd=.35)
 for(i in 1:16) {
  stroke(9,row_y[i]-4.5,252,row_y[i]-4.5,col='#EDF0F2',lwd=.35)
  label<-wrap(uses[i],76,row_size)
  stopifnot(length(strsplit(label,'\n')[[1]])<=2L)
  txt(label,9,row_y[i],row_size)
  txt(rowSums(tab)[i],96,row_y[i],10.2,col=muted,just='centre')
  for(j in 1:9) if(tab[i,j]>0) {
   n<-as.integer(tab[i,j]);rad<-radius(n)
   circle(column_x[j],row_y[i],rad,colours[j])
   stopifnot(measure(as.character(n),9)<2*rad-.2)
   txt(n,column_x[j],row_y[i],9,col=number_colours[j],just='centre',face='bold')
  }
 }
 # Compact structure key retains full names, so this panel can be read alone.
 for(j in 1:9) {
  col<-(j-1)%%3;row<-(j-1)%/%3
  x<-9+85*col;y<-71-18*row
  circle(x+2.4,y,2.4,colours[j]);txt(codes[j],x+2.4,y,8.3,col=number_colours[j],just='centre',face='bold')
  label<-wrap(class_key$label[j],71,8.8)
  stopifnot(length(strsplit(label,'\n')[[1]])<=2L)
  txt(label,x+8,y,8.8)
 }
 txt('Compounds per cell',9,13,9.2,col=muted)
 for(j in 1:4) {
  n<-c(1,3,6,9)[j];x<-c(64,80,98,118)[j]
  circle(x,13,radius(n),'#D6DFE4');txt(n,x,13,9,just='centre',face='bold')
 }
 txt('101 compounds',251,13,9.5,col=muted,just='right')
}
for(fmt in c('pdf','svg','png','preview.png')) {
 path<-file.path(out,paste0('Level1_structure_use_matrix.',fmt))
 if(fmt=='pdf') grDevices::cairo_pdf(path,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg') svglite::svglite(path,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png') ragg::agg_png(path,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(path,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(source_paths,sha,character(1)),source_paths)))
for(f in names(tree_manifest$output_hashes)) stopifnot(sha(file.path(tree_out,f))==tree_manifest$output_hashes[[f]])
writeLines(c('Structure classes and primary uses of the 101 Level 1 compounds.',
 'Rows show the 16 user-supplied primary-use categories, ordered by decreasing compound count, with alphabetical ordering for tied counts. Columns A-I and their colours match the large-font classification tree. Row and column margins give totals. Each compound contributes to exactly one cell; the complete 16 x 9 matrix sums to 101.',
 'Circle area is proportional to the number of compounds in a cell. Numbers inside circles are exact counts. Empty intersections represent zero compounds. No compounds or use classes are omitted, and no minimum-count threshold is applied.',
 'Primary use is the supplied general-use annotation, not an inferred function within plastics. Detailed multi-use annotations do not enter this single-primary-use cross-tabulation. Structural groups and Level 1 membership match the existing classification tree; this panel does not recalculate scores or ranks.',
 'The two panels are exported separately for review. The existing 11.5 pt classification tree files are preserved byte for byte. The matrix is 260 x 260 mm, with 10.2 pt use labels and 9 pt counts; final joint manuscript layout remains to be set.'),file.path(module,'captions.txt'))
paths<-list.files(out,full.names=TRUE);paths<-paths[basename(paths)!='manifest.json']
manifest<-list(status='review',backend='R',width_mm=260,height_mm=260,row_label_font_pt=row_size,
 cohort=101,rows=16,columns=9,total_count=sum(tab),nonzero_cells=sum(tab>0),zero_cells=sum(tab==0),max_cell=max(tab),
 row_totals=as.list(setNames(as.integer(rowSums(tab)),uses)),
 column_totals=as.list(setNames(as.integer(colSums(tab)),unname(codes))),
 circle_area_proportional=TRUE,zero_cells_blank=TRUE,excluded_compounds=0,
 tree_preserved_byte_for_byte=TRUE,source_scores_ranks_unchanged=TRUE,
 source_hashes=as.list(before),classification=classification,
 script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(paths,sha,character(1)),basename(paths))),
 source_data_hashes=as.list(setNames(vapply(list.files(data_out,full.names=TRUE),sha,character(1)),list.files(data_out))),
 qa_notes=c('R parse confirmed by successful execution; wider review dimensions explicitly selected',
 'Use labels 10.2 pt; counts 9 pt; 8.8 pt structure key; exact bubble diameters checked against text widths',
 'TIFF omitted for review: editable PDF/SVG and 600 dpi PNG exported'))
jsonlite::write_json(manifest,file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat('Created 16 x 9 bubble matrix; 101 compounds in 40 nonzero cells. Existing tree unchanged.\n')
