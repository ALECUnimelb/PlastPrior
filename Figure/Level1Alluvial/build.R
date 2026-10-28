stop("This experimental export is retired. Use the current figure entrypoints in Figure/INDEX.md.")
#!/usr/bin/env Rscript
# Three-way membership bands, built from the complete observed triples.
# Review width_mm = 430, height_mm = 350; Arial 11.5 pt labels.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root,'Figure/Level1Alluvial')
out <- file.path(root,'result/figures',basename(module),'images')
data_out <- file.path(root,'result/figures/Level1Alluvial/review/data')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source_dir <- file.path(root,'result/figures/Level1Composition/review/data')
read <- function(p) as.data.frame(readr::read_csv(p,show_col_types=FALSE))
sha <- function(p) digest::digest(file=p,algo='sha256',serialize=FALSE)
source_paths <- c(list.files(source_dir,full.names=TRUE),file.path(root,'result/PlastPrior_results.csv'))
old_modules <- c('Level1Evidence','Level1Identity','Level1IdentityTree','Level1UseMatrix','Level1UseTreemap','Level1Composition')
protected <- c(source_paths,unlist(lapply(old_modules,function(m)list.files(file.path(root,'result/figures',m,'images'),full.names=TRUE))))
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
r <- read(file.path(source_dir,'reg_counts.csv'))
names(d)[names(d)=='GIC_regulatory_status'] <- 'regulatory_status'
f <- aggregate(rep(1L,nrow(d)),d[,c('primary_use','structure_group','regulatory_status')],sum)
names(f)[4] <- 'n';f$flow_id <- sprintf('F%02d',seq_len(nrow(f)))
stopifnot(nrow(f)==59L,sum(f$n)==101L,sum(f$n==1L)==37L)

# Crossings between distinct nodes, weighted by the number of compound pairs.
# This is a deterministic layout objective, not a chemical rank or similarity.
crossings <- function(u_order,s_order) {
 a<-match(f$primary_use,u_order);b<-match(f$structure_group,s_order);c<-match(f$regulatory_status,r$category)
 pairs<-combn(seq_len(nrow(f)),2);i<-pairs[1,];j<-pairs[2,]
 sum(f$n[i]*f$n[j]*(((a[i]-a[j])*(b[i]-b[j])<0)+((b[i]-b[j])*(c[i]-c[j])<0)))
}
u_order <- u$category;s_order <- s$category
initial_crossings <- crossings(u_order,s_order)
for(iter in 1:100) {
 improvement<-FALSE
 for(axis in c('use','structure')) {
  ord<-if(axis=='use')u_order else s_order
  for(k in seq_len(length(ord)-1)) {
   candidate<-ord;candidate[c(k,k+1)]<-candidate[c(k+1,k)]
   score<-if(axis=='use')crossings(candidate,s_order) else crossings(u_order,candidate)
   if(score<crossings(u_order,s_order)) {
    ord<-candidate
    if(axis=='use')u_order<-ord else s_order<-ord
    improvement<-TRUE
   }
  }
 }
 if(!improvement)break
}
u<-u[match(u_order,u$category),];s<-s[match(s_order,s$category),]
reg_colours <- setNames(c('#A7655E','#BD9451','#87739E','#648F9F','#94A18A'),r$category)
f$colour <- unname(reg_colours[f$regulatory_status])
width_mm<-430;height_mm<-350;font<-'Arial';ink<-'#26343D'
unit_h<-1.8;body_bottom<-15;body_top<-320
invisible(ragg::agg_capture(width=1600,height=1200,res=300))
label_width<-function(z)convertWidth(grobWidth(textGrob(z,gp=gpar(fontfamily=font,fontsize=11.5))),'mm',valueOnly=TRUE)
wrap_label<-function(z,max_width) {
 lines<-character()
 for(paragraph in strsplit(z,'\n',fixed=TRUE)[[1]]) {
  current<-''
  for(word in strsplit(paragraph,' ',fixed=TRUE)[[1]]) {
   candidate<-if(nzchar(current))paste(current,word) else word
   if(nzchar(current)&&label_width(candidate)>max_width) {lines<-c(lines,current);current<-word}
   else current<-candidate
  }
  lines<-c(lines,current)
 }
 stopifnot(all(vapply(lines,label_width,numeric(1))<=max_width))
 paste(lines,collapse='\n')
}
u$display_label<-vapply(paste0(u$label,'  ',u$n),wrap_label,character(1),max_width=73)
s$display_label<-vapply(paste0(s$label,'  ',s$n),wrap_label,character(1),max_width=53)
r$display_label<-vapply(paste0(r$label,'  ',r$n),wrap_label,character(1),max_width=85)
grDevices::dev.off()

# Label slots may be taller than the actual count-scaled node. The latter always
# has height n * unit_h. This preserves ribbon thickness for small categories.
nodes <- function(tbl,axis) {
 lines<-vapply(strsplit(tbl$display_label,'\n',fixed=TRUE),length,integer(1))
 tbl$slot_height<-pmax(tbl$n*unit_h,lines*4.6+2)
 gap<-4.2
 total<-sum(tbl$slot_height)+gap*(nrow(tbl)-1)
 stopifnot(total<=body_top-body_bottom)
 y<-body_top-(body_top-body_bottom-total)/2
 tbl$centre<-tbl$top<-tbl$bottom<-NA_real_
 for(i in seq_len(nrow(tbl))) {
  tbl$centre[i]<-y-tbl$slot_height[i]/2
  tbl$top[i]<-tbl$centre[i]+tbl$n[i]*unit_h/2
  tbl$bottom[i]<-tbl$centre[i]-tbl$n[i]*unit_h/2
  y<-y-tbl$slot_height[i]-gap
 }
 tbl$axis<-axis;tbl
}
un<-nodes(u,'use');sn<-nodes(s,'structure');rn<-nodes(r,'regulatory')
f$u_top<-f$s_top<-f$r_top<-NA_real_
for(axis in c('u','s','r')) {
 nd<-get(paste0(axis,'n'));field<-switch(axis,u='primary_use',s='structure_group',r='regulatory_status')
 for(i in seq_len(nrow(nd))) {
  ix<-which(f[[field]]==nd$category[i])
  # Exactly the same slots on the incoming and outgoing middle node retain
  # each full triple instead of mixing alluvia at the structural axis.
  ord<-switch(axis,
   u=order(match(f$structure_group[ix],s_order),match(f$regulatory_status[ix],r$category)),
   s=order(match(f$regulatory_status[ix],r$category),match(f$primary_use[ix],u_order)),
   r=order(match(f$structure_group[ix],s_order),match(f$primary_use[ix],u_order)))
  ix<-ix[ord];heights<-f$n[ix]*unit_h
  f[[paste0(axis,'_top')]][ix]<-nd$top[i]-c(0,head(cumsum(heights),-1))
  stopifnot(abs(sum(heights)-(nd$top[i]-nd$bottom[i]))<1e-8)
 }
 f[[paste0(axis,'_bottom')]]<-f[[paste0(axis,'_top')]]-f$n*unit_h
}
stopifnot(!anyNA(f))
for(axis in c('u','s','r')) stopifnot(all(abs(f[[paste0(axis,'_top')]]-f[[paste0(axis,'_bottom')]]-f$n*unit_h)<1e-8))
readr::write_csv(f,file.path(data_out,'triple_flows.csv'))
readr::write_csv(rbind(un,sn,rn),file.path(data_out,'axis_nodes.csv'))
readr::write_csv(d,file.path(data_out,'compound_membership.csv'))

txt<-function(label,x,y,size=11.5,just='left',bold=FALSE,col=ink) grid.text(label,
 x=unit(x,'mm'),y=unit(y,'mm'),just=just,
 gp=gpar(fontfamily=font,fontsize=size,fontface=if(bold)'bold' else 'plain',col=col,lineheight=.98))
rect<-function(x,y,w,h,fill,col=NA,lwd=.3)grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),
 just=c('left','bottom'),gp=gpar(fill=fill,col=col,lwd=lwd))
ribbon<-function(x0,x1,top0,top1,h,colour) {
 t<-seq(0,1,length.out=80)
 xx<-(1-t)^3*x0+3*(1-t)^2*t*(x0+.42*(x1-x0))+3*(1-t)*t^2*(x1-.42*(x1-x0))+t^3*x1
 yy<-(1-(3*t^2-2*t^3))*top0+(3*t^2-2*t^3)*top1
 grid.polygon(x=unit(c(xx,rev(xx)),'mm'),y=unit(c(yy,rev(yy-h)),'mm'),
  gp=gpar(fill=grDevices::adjustcolor(colour,alpha.f=.75),col='white',lwd=.18))
}
draw<-function() {
 grid.newpage()
 txt('Primary uses',78,337,14,just='right',bold=TRUE)
 txt('Structural classes',211,337,14,just='centre',bold=TRUE)
 txt('GIC regulatory annotations',337,337,14,bold=TRUE)
 for(i in order(-f$n,f$flow_id)) {
  ribbon(85,180,f$u_top[i],f$s_top[i],f$n[i]*unit_h,f$colour[i])
  ribbon(242,330,f$s_top[i],f$r_top[i],f$n[i]*unit_h,f$colour[i])
 }
 # The narrow strips retain the true count scale, with the colour on both
 # sides of the middle label column showing uninterrupted triple membership.
 for(i in seq_len(nrow(f))) {
  rect(82,f$u_bottom[i],3,f$n[i]*unit_h,f$colour[i])
  rect(180,f$s_bottom[i],2,f$n[i]*unit_h,f$colour[i])
  rect(240,f$s_bottom[i],2,f$n[i]*unit_h,f$colour[i])
  rect(330,f$r_bottom[i],3,f$n[i]*unit_h,f$colour[i])
 }
 for(i in seq_len(nrow(un)))txt(un$display_label[i],78,un$centre[i],just='right')
 for(i in seq_len(nrow(sn))) {
  rect(183,sn$centre[i]-sn$slot_height[i]/2,56,sn$slot_height[i],'#F3F5F6')
  txt(sn$display_label[i],211,sn$centre[i],just='centre')
 }
 for(i in seq_len(nrow(rn)))txt(rn$display_label[i],337,rn$centre[i])
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_alluvial.',fmt))
 if(fmt=='pdf')grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg')svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png')ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(protected,sha,character(1)),protected)))
writeLines(c('Primary use, structural class and GIC annotation of the 101 Level 1 compounds.',
 'Each ribbon represents one of the 59 observed three-way combinations. Ribbon thickness is proportional to the number of unique compounds, with a common scale of 1.8 mm per compound across all axes. Regulatory annotation determines colour throughout the path. The incoming and outgoing positions at the structural axis retain exactly the same triple identity and thickness.',
 'The 16 use categories, nine structural groups and five regulatory categories include all 101 compounds without exclusions or regrouping. Narrow vertical strips carry count-scaled heights. Gaps and pale label backgrounds provide legible text and do not encode quantity. Category ordering is optimised for weighted crossings and does not change the original chemical scores or ranks.',
 'This is descriptive correspondence, not temporal flow or a causal claim. Uses and structural groups retain the definitions from the preceding figures; X denotes F, Cl, Br or I. GIC annotations describe the saved database rather than current jurisdiction-specific legal status. The complete name list and all previous figures remain unchanged.',
 'Review proof: 430 x 350 mm; 11.5 pt labels, 14 pt headings. All drawing and exports use R.'),file.path(module,'caption.txt'))
outputs<-list.files(out,full.names=TRUE);outputs<-outputs[basename(outputs)!='manifest.json']
jsonlite::write_json(list(status='review',backend='R',cohort=101,triples=59,singleton_triples=37,
 axis_categories=c(16,9,5),unit_height_mm=unit_h,width_mm=width_mm,height_mm=height_mm,label_font_pt=11.5,
 weighted_crossings_initial=initial_crossings,weighted_crossings_final=crossings(u_order,s_order),
 optimisation_scope='Adjacent node-order swaps; not a guarantee of global minimum or all ribbon-level crossings',
 scores_ranks_unchanged=TRUE,previous_figures_unchanged=TRUE,
 protected_hashes=as.list(before),script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(outputs,sha,character(1)),basename(outputs))),
 qa_notes=c('Actual R execution checks syntax; Arial text sizes are in grid helpers',
 '430 mm review proof to retain readable labels; not final journal width',
 '600 dpi PNG plus PDF/SVG; TIFF not requested','Pale label blocks and gaps are not quantitative')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat('Rendered 59 complete three-way combinations containing all 101 compounds.\n')
