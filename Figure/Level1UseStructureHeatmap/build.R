#!/usr/bin/env Rscript
# Primary uses on rows, structural classes on columns; full count matrix.
# Review width_mm = 390, height_mm = 245; Arial 11.5 pt labels.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root,'Figure/Level1UseStructureHeatmap')
out <- file.path(module,'output')
data_out <- file.path(root,'output/figure_data/Level1UseStructureHeatmap/review')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source_dir <- file.path(root,'output/figure_data/Level1Composition/review')
read <- function(p)as.data.frame(readr::read_csv(p,show_col_types=FALSE))
sha <- function(p)digest::digest(file=p,algo='sha256',serialize=FALSE)
old_modules <- c('Level1Evidence','Level1Identity','Level1IdentityTree','Level1UseMatrix',
 'Level1UseTreemap','Level1Composition','Level1Alluvial','Level1GroupedStacked','Level1UseStructureUpSet')
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
u <- u[order(-u$n,u$category,method='radix'),]
structure_order <- c('hal_non_aromatic','hal_aromatic_chx','hal_aromatic_o','hal_aromatic_ns','hal_heterocycle',
 'nonhal_aromatic_ch','nonhal_o','nonhal_heterocycle','nonhal_other')
s <- s[match(structure_order,s$category),]
s$header_family <- c(rep('Halogenated',5),rep('Non-halogenated',4))
s$column_label <- c('Non-aromatic','Aromatic\nC/H/X only','Aromatic\nO-containing','Aromatic\nN/S-containing',
 'Heteroaromatic','Aromatic\nhydrocarbons','O-containing','Heteroaromatic','Other')
m <- table(factor(d$primary_use,levels=u$category),factor(d$structure_group,levels=s$category))
stopifnot(identical(dim(m),c(16L,9L)),sum(m)==101L,sum(m>0)==40L,sum(m==0)==104L,max(m)==9L,
 all(rowSums(m)==u$n),all(colSums(m)==s$n))
cells <- expand.grid(row_index=seq_len(nrow(u)),column_index=seq_len(nrow(s)))
cells$primary_use <- u$category[cells$row_index]
cells$structure_group <- s$category[cells$column_index]
cells$n <- as.integer(m[cbind(cells$row_index,cells$column_index)])
cells$display_label <- ifelse(cells$n>0,as.character(cells$n),'')
width_mm<-390;height_mm<-245;font<-'Arial';ink<-'#26343D'
matrix_x<-87;matrix_y<-36;cell_w<-31;cell_h<-10
cells$x_mm<-matrix_x+(cells$column_index-.5)*cell_w
cells$y_mm<-matrix_y+(16-cells$row_index+.5)*cell_h
palette<-grDevices::colorRampPalette(c('#FFFFFF','#C9DDE0','#2F6F79'))(10)
cells$colour<-palette[cells$n+1L]
u$y_mm<-matrix_y+(16-seq_len(nrow(u))+.5)*cell_h
s$x_mm<-matrix_x+(seq_len(nrow(s))-.5)*cell_w
invisible(ragg::agg_capture(width=1600,height=1200,res=300))
metrics<-function(z,size=11.5) {
 g<-textGrob(z,gp=gpar(fontfamily=font,fontsize=size,lineheight=.98))
 c(w=convertWidth(grobWidth(g),'mm',valueOnly=TRUE),h=convertHeight(grobHeight(g),'mm',valueOnly=TRUE))
}
um<-t(vapply(u$label,metrics,numeric(2)));sm<-t(vapply(s$column_label,metrics,numeric(2)))
stopifnot(all(um[,'w']<77),all(um[,'h']<cell_h-1),all(sm[,'w']<cell_w-1),all(sm[,'h']<12))
grDevices::dev.off()
readr::write_csv(d,file.path(data_out,'compound_membership.csv'))
readr::write_csv(cells,file.path(data_out,'heatmap_cells.csv'))
readr::write_csv(u,file.path(data_out,'row_key.csv'))
readr::write_csv(s,file.path(data_out,'column_key.csv'))
wide<-data.frame(primary_use=u$category,as.data.frame.matrix(m),check.names=FALSE)
readr::write_csv(wide,file.path(data_out,'count_matrix.csv'))
txt<-function(z,x,y,size=11.5,bold=FALSE,just='left',col=ink)grid.text(z,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold)'bold' else 'plain',col=col,lineheight=.98))
rect<-function(x,y,w,h,fill,col=NA,lwd=.4)grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),
 just=c('left','bottom'),gp=gpar(fill=fill,col=col,lwd=lwd))
line<-function(x1,y1,x2,y2,col='#B8C5CA',lwd=.6)grid.lines(unit(c(x1,x2),'mm'),unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
luminance<-function(col){v<-as.numeric(grDevices::col2rgb(col))/255;v<-ifelse(v<=.04045,v/12.92,((v+.055)/1.055)^2.4);sum(v*c(.2126,.7152,.0722))}
number_colour<-function(bg)if((luminance(bg)+.05)/.05>1.05/(luminance(bg)+.05))'#000000' else '#FFFFFF'
draw<-function() {
 grid.newpage()
 txt('Primary use',matrix_x-4,208,13,TRUE,just='right')
 txt('Halogenated',matrix_x+cell_w*2.5,229,13,TRUE,just='centre')
 txt('Non-halogenated',matrix_x+cell_w*7,229,13,TRUE,just='centre')
 line(matrix_x+1,222,matrix_x+5*cell_w-1,222)
 line(matrix_x+5*cell_w+1,222,matrix_x+9*cell_w-1,222)
 for(j in seq_len(nrow(s)))txt(s$column_label[j],s$x_mm[j],208,11.5,just='centre')
 for(i in seq_len(nrow(cells))) {
  q<-cells[i,]
  rect(q$x_mm-cell_w/2,q$y_mm-cell_h/2,cell_w,cell_h,q$colour,col='#DCE4E7',lwd=.4)
  if(q$n>0)txt(q$display_label,q$x_mm,q$y_mm,12,just='centre',col=number_colour(q$colour))
 }
 line(matrix_x+5*cell_w,matrix_y,matrix_x+5*cell_w,matrix_y+16*cell_h,col='#ABBBC1',lwd=.8)
 for(i in seq_len(nrow(u)))txt(u$label[i],matrix_x-4,u$y_mm[i],11.5,just='right')
 # Discrete count key, including zero as white. No missing observations.
 key_x<-matrix_x+9*cell_w/2-30
 txt('Number of compounds',key_x+30,25,11.5,just='centre')
 for(n in 0:9) {
  rect(key_x+n*6,12,6,5,palette[n+1],col='#DCE4E7',lwd=.3)
  txt(n,key_x+(n+.5)*6,7,10.5,just='centre')
 }
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_use_structure_heatmap.',fmt))
 if(fmt=='pdf')grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg')svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png')ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(protected,sha,character(1)),protected)))
writeLines(c('Primary uses and structural classes of the 101 Level 1 compounds.',
 'Rows represent the 16 primary uses, ordered by descending compound count with alphabetical tie-breaking. Columns represent the existing nine mutually exclusive structural classes. The two header families shorten the column labels without changing class definitions or assignments. X denotes F, Cl, Br or I; O, oxygen; N, nitrogen; S, sulfur.',
 'Each cell gives the number of compounds assigned to both categories. Positive counts are printed and encoded by one shared sequential 0-9 colour scale. White unlabelled cells are zero, not missing data. The full 144-cell matrix is shown, with 40 positive cells. All 101 compounds are counted once; no normalization, clustering, hypothesis tests or inferential claims are used.',
 'Halogenated aromatic N/S-containing compounds may also contain O; structural categories retain the ordered classification rules from the original structure report. General primary-use annotations are not asserted to be functions specific to plastics. The plot shows descriptive classification correspondence rather than causation.',
 'Five-level Level 1 membership, scores, ranks, Top-n flags and previous figures are unchanged. Regulatory annotations are retained in the saved cohort but are not encoded here. Review proof: 390 x 245 mm, Arial 11.5 pt category labels and 12 pt cell counts. All drawing and export use R.'),file.path(module,'caption.txt'))
files<-list.files(out,full.names=TRUE);files<-files[basename(files)!='manifest.json']
jsonlite::write_json(list(status='review',backend='R',cohort=101,use_rows=16,structure_columns=9,
 cells=144,positive_cells=40,zero_cells=104,total_cell_count=101,maximum_cell_count=9,
 width_mm=width_mm,height_mm=height_mm,label_font_pt=11.5,cell_font_pt=12,
 excluded_compounds=0,scores_ranks_unchanged=TRUE,previous_figures_unchanged=TRUE,
 protected_hashes=as.list(before),script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(files,sha,character(1)),basename(files))),
 qa_notes=c('R execution checks syntax; explicit measured text fitting before export',
 '390 mm review proof for horizontal labels; not final journal sizing',
 'PDF/SVG, 600 dpi PNG and 300 dpi preview; TIFF not requested',
 'Full matrix and all 101 compounds retained; white cells are exact zeros')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat('Heatmap exported: 16 uses x 9 structural classes; all 101 compounds, 40 positive cells.\n')
