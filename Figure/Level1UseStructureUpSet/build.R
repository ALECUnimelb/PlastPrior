stop("This experimental export is retired. Use the current figure entrypoints in Figure/INDEX.md.")
#!/usr/bin/env Rscript
# Standard UpSet for all primary-use and structural-class intersections.
# Review width_mm = 400, height_mm = 350; Arial 11.5 pt set labels.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root,'Figure/Level1UseStructureUpSet')
out <- file.path(root,'result/figures',basename(module),'images')
data_out <- file.path(root,'result/figures/Level1UseStructureUpSet/review/data')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source_dir <- file.path(root,'result/figures/Level1Composition/review/data')
read <- function(p)as.data.frame(readr::read_csv(p,show_col_types=FALSE))
sha <- function(p)digest::digest(file=p,algo='sha256',serialize=FALSE)
old_modules <- c('Level1Evidence','Level1Identity','Level1IdentityTree','Level1UseMatrix',
 'Level1UseTreemap','Level1Composition','Level1Alluvial','Level1GroupedStacked')
protected <- c(list.files(source_dir,full.names=TRUE),file.path(root,'result/PlastPrior_results.csv'),
 unlist(lapply(old_modules,function(m)list.files(file.path(root,'result/figures',m,'images'),full.names=TRUE))))
before <- setNames(vapply(protected,sha,character(1)),protected)
d <- read(file.path(source_dir,'compound_membership.csv'))
full <- read(file.path(root,'result/PlastPrior_results.csv'))
idx <- match(d$inchikey,full$inchikey)
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),!anyNA(idx),all(d$Figure_priority_level==1),
 setequal(d$inchikey,full$inchikey[full$Hazard_score>=12 & full$Exposure_score>=12]))
for(f in c('Name','CAS','SMILES','Hazard_score','Exposure_score','Priority_score','Priority_rank','Top_n_selected','GIC_regulatory_status'))
 stopifnot(identical(as.character(d[[f]]),as.character(full[[f]][idx])))
u <- read(file.path(source_dir,'use_counts.csv'))
s <- read(file.path(source_dir,'structure_counts.csv'))
u <- u[order(-u$n,u$category,method='radix'),]
s <- s[order(-s$n,s$category,method='radix'),]
u$family <- 'Primary use';s$family <- 'Structural class'
sets <- rbind(u,s);rownames(sets)<-NULL
sets$set_id <- c(sprintf('U%02d',1:nrow(u)),sprintf('S%02d',1:nrow(s)))
sets$colour <- ifelse(sets$family=='Primary use','#347681','#687FA9')
intersections <- aggregate(rep(1L,nrow(d)),d[,c('primary_use','structure_group')],sum)
names(intersections)[3]<-'n'
intersections <- intersections[order(-intersections$n,match(intersections$primary_use,u$category),
 match(intersections$structure_group,s$category)),]
intersections$intersection_id <- sprintf('I%02d',seq_len(nrow(intersections)))
intersections$use_set_id <- sets$set_id[match(intersections$primary_use,sets$category)]
intersections$structure_set_id <- sets$set_id[match(intersections$structure_group,sets$category)]
pair_key<-function(use,structure)paste(use,structure,sep=' | ')
d$intersection_id <- intersections$intersection_id[match(pair_key(d$primary_use,d$structure_group),
 pair_key(intersections$primary_use,intersections$structure_group))]
stopifnot(nrow(sets)==25L,nrow(intersections)==40L,sum(intersections$n)==101L,
 all(c(sum(u$n),sum(s$n))==101L),!anyNA(d$intersection_id))
membership <- do.call(rbind,lapply(seq_len(nrow(intersections)),function(j) data.frame(
 intersection_id=intersections$intersection_id[j],set_id=sets$set_id,
 active=sets$set_id%in%c(intersections$use_set_id[j],intersections$structure_set_id[j]),
 compound_count=intersections$n[j])))
stopifnot(all(tapply(membership$active,membership$intersection_id,sum)==2))
for(i in seq_len(nrow(sets))) stopifnot(sum(membership$compound_count[membership$set_id==sets$set_id[i]&membership$active])==sets$n[i])

width_mm<-400;height_mm<-350;font<-'Arial';ink<-'#26343D'
row_h<-9.5;matrix_top<-267;family_gap<-13
sets$y_mm<-c(matrix_top-row_h*((1:16)-.5),matrix_top-row_h*16-family_gap-row_h*((1:9)-.5))
matrix_left<-146;pitch<-6;matrix_width<-pitch*nrow(intersections)
intersections$x_mm<-matrix_left+pitch*(seq_len(nrow(intersections))-.5)
intersection_base<-288;intersection_height<-45;intersection_max<-10
intersections$height_mm<-intersection_height*intersections$n/intersection_max
set_zero<-50;set_width<-36;set_max<-35
sets$bar_width_mm<-sets$n*set_width/set_max
invisible(ragg::agg_capture(width=1600,height=1200,res=300))
metrics <- t(vapply(sets$label,function(label){
 g<-textGrob(label,gp=gpar(fontfamily=font,fontsize=11.5,lineheight=.98))
 c(w=convertWidth(grobWidth(g),'mm',valueOnly=TRUE),h=convertHeight(grobHeight(g),'mm',valueOnly=TRUE))
},numeric(2)))
stopifnot(max(metrics[,'w'])<76,max(metrics[,'h'])<row_h-.5)
grDevices::dev.off()
readr::write_csv(d,file.path(data_out,'compound_membership.csv'))
readr::write_csv(intersections,file.path(data_out,'intersections.csv'))
readr::write_csv(sets,file.path(data_out,'sets.csv'))
readr::write_csv(membership,file.path(data_out,'intersection_membership.csv'))

txt<-function(z,x,y,size=11.5,bold=FALSE,just='left',col=ink)grid.text(z,x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold)'bold' else 'plain',col=col,lineheight=.98))
rect<-function(x,y,w,h,fill,col=NA,lwd=.4)grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),
 just=c('left','bottom'),gp=gpar(fill=fill,col=col,lwd=lwd))
line<-function(x1,y1,x2,y2,col=ink,lwd=.6)grid.lines(unit(c(x1,x2),'mm'),unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
dot<-function(x,y,r,fill)grid.circle(x=unit(x,'mm'),y=unit(y,'mm'),r=unit(r,'mm'),gp=gpar(fill=fill,col=NA))
draw<-function() {
 grid.newpage()
 txt('Intersection size',matrix_left,342,13.5,TRUE)
 for(t in seq(0,10,2)) {
  yy<-intersection_base+intersection_height*t/intersection_max
  if(t>0)line(matrix_left,yy,matrix_left+matrix_width,yy,col='#E8ECEF',lwd=.35)
  line(matrix_left-1.2,yy,matrix_left,yy,col=ink)
  txt(t,matrix_left-2.5,yy,11,just='right')
 }
 line(matrix_left,intersection_base,matrix_left,intersection_base+intersection_height)
 line(matrix_left,intersection_base,matrix_left+matrix_width,intersection_base)
 for(j in seq_len(nrow(intersections))) {
  q<-intersections[j,]
  rect(q$x_mm-1.9,intersection_base,3.8,q$height_mm,'#3C515E')
  txt(q$n,q$x_mm,intersection_base+q$height_mm+2.7,11,just='centre')
 }
 txt('Set size',32,277,12,TRUE,just='centre')
 txt('Primary uses',134,277,13,TRUE,just='right',col='#347681')
 txt('Intersection membership',matrix_left+matrix_width/2,277,12,TRUE,just='centre')
 txt('Structural classes',134,108,13,TRUE,just='right',col='#687FA9')
 for(i in seq_len(nrow(sets))) {
  yy<-sets$y_mm[i]
  if(i%%2==0)rect(9,yy-row_h/2,381,row_h,'#F6F8F9')
  rect(set_zero-sets$bar_width_mm[i],yy-2.65,sets$bar_width_mm[i],5.3,sets$colour[i])
  txt(sets$n[i],set_zero-sets$bar_width_mm[i]-1.6,yy,11,just='right')
  txt(sets$label[i],134,yy,11.5,just='right')
  dot(intersections$x_mm,rep(yy,nrow(intersections)),.42,'#E0E5E8')
 }
 for(j in seq_len(nrow(intersections))) {
  ix<-match(c(intersections$use_set_id[j],intersections$structure_set_id[j]),sets$set_id)
  xx<-intersections$x_mm[j]
  line(xx,sets$y_mm[ix[1]],xx,sets$y_mm[ix[2]],col='#A4AEB4',lwd=.7)
  for(i in ix)dot(xx,sets$y_mm[i],1.13,sets$colour[i])
 }
 # Leftward set-size axis; tick values make the reversed direction explicit.
 set_axis_y<-11
 line(set_zero-set_width,set_axis_y,set_zero,set_axis_y)
 for(t in c(0,10,20,30)) {
  xx<-set_zero-set_width*t/set_max
  line(xx,set_axis_y,xx,set_axis_y-1)
  txt(t,xx,set_axis_y-3.7,10.5,just='centre')
 }
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_use_structure_upset.',fmt))
 if(fmt=='pdf')grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg')svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png')ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(protected,sha,character(1)),protected)))
writeLines(c('Primary-use and structural-class intersections of the 101 Level 1 compounds.',
 'The UpSet plot includes all 16 primary-use sets, nine structural-class sets and 40 observed exclusive intersections. Each column links one use and one structural class; the bar above gives their joint count. Every compound belongs to exactly one use and one structural class, so each observed intersection contains exactly two active sets. Light inactive dots denote non-membership. No top-intersection filter is applied.',
 'Leftward horizontal bars show marginal set sizes, using the same zero-based scale for both families. Upper bars show intersection sizes, ordered descending; ties follow use and structure display orders. Sets are ordered by size within each family, with alphabetical tie-breaking. Intersections are disjoint and sum to 101; marginal sizes sum to 101 in each family, or 202 over both families because every compound belongs to two sets.',
 'Teal identifies primary-use sets, blue identifies structural-class sets; intersection bars are neutral. Existing structure and use definitions are retained. X denotes F, Cl, Br or I. Regulatory annotations are retained in the source table but not encoded in this use-structure figure. No compound was excluded or assigned to a new class.',
 'The five-level Level 1 cohort, original scores, ranks and Top-n selection are unchanged. This figure describes categorical correspondence and does not imply causal relationships or molecular similarity. Previous figures and the complete name list remain unchanged. No inferential statistics apply.',
 'Review proof 400 x 350 mm, Arial 11.5 pt set labels and 11 pt bar counts. R-only PDF/SVG and raster exports.'),file.path(module,'caption.txt'))
files<-list.files(out,full.names=TRUE);files<-files[basename(files)!='manifest.json']
jsonlite::write_json(list(status='review',backend='R',cohort=101,use_sets=16,structure_sets=9,
 observed_exclusive_intersections=40,intersection_sum=101,marginal_sums_by_family=c(101,101),
 active_sets_per_intersection=2,top_n_filter=FALSE,excluded_compounds=0,
 width_mm=width_mm,height_mm=height_mm,set_label_font_pt=11.5,bar_count_font_pt=11,
 scores_ranks_unchanged=TRUE,previous_figures_unchanged=TRUE,
 protected_hashes=as.list(before),script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(files,sha,character(1)),basename(files))),
 qa_notes=c('Actual R execution checks parsing; font sizes in grid helpers',
 '400 mm review proof for large labels; not final journal sizing',
 'PDF/SVG, 600 dpi PNG and 300 dpi preview; TIFF not requested',
 'Counts rebuilt from compound-level assignments and all 40 intersections retained')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat('UpSet exported: 25 sets, 40 exclusive intersections, all 101 compounds.\n')
