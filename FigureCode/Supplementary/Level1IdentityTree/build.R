#!/usr/bin/env Rscript
# A categorical radial tree: Level 1 -> nine structure groups -> 101 compounds.
# Membership only: branch length, angular position and colour encode no ranking
# or molecular similarity. R/grid drawing, Arial, editable PDF/SVG, 600 dpi PNG.
# width_mm = 380, height_mm = 380: a full-name review figure, not a reduced print.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
source(file.path(root,'FigureCode/_shared/result_paths.R'))
module <- file.path(root,'FigureCode/Supplementary/Level1IdentityTree')
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1) stop('Run through FigureCode/run_retained.py')
out <- args[[1]]
data_dir <- file.path(root,'result/figure_data/Level1Identity')
tree_data <- file.path(out,'source_data')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(tree_data,recursive=TRUE,showWarnings=FALSE)
source(file.path(root,'FigureCode/_shared/theme.R'))
font <- resolve_manuscript_font()
d <- read.csv(file.path(data_dir,'compound_identity.csv'),stringsAsFactors=FALSE,check.names=FALSE)
report <- jsonlite::fromJSON(file.path(data_dir,'classification.json'))
sha <- function(p) digest::digest(file=p,algo='sha256',serialize=FALSE)
input_hash <- sha(file.path(data_dir,'compound_identity.csv'))
for(p in names(report$source_hashes)) stopifnot(sha(relocated_result_path(root,p))==report$source_hashes[[p]])
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),all(d$inchikey==d$regenerated_inchikey))
groups <- c('hal_non_aromatic','hal_aromatic_chx','hal_aromatic_o','hal_aromatic_ns','hal_heterocycle',
            'nonhal_aromatic_ch','nonhal_o','nonhal_heterocycle','nonhal_other')
colours <- setNames(c('#3A7582','#687FA9','#947BAC','#AA8650','#A45F62','#658B66','#B18B60','#8C7E71','#73848F'),groups)
codes <- setNames(LETTERS[1:9],groups)
centre <- 190
width_mm <- height_mm <- 380
body_size <- 11.5
label_radius <- 114
label_width <- 65
measure <- function(s) convertWidth(grobWidth(textGrob(s,gp=gpar(fontfamily=font,fontsize=body_size))),'mm',valueOnly=TRUE)
wrap <- function(s) {
 chars<-strsplit(s,'',fixed=TRUE)[[1]];result<-character();current<-''
 for(ch in chars) {
  if(nzchar(current)&&measure(paste0(current,ch))>label_width) {
   br<-gregexpr('[ ,;-]',current)[[1]];br<-tail(br[br>0],1)
   if(length(br)&&br>nchar(current)*.2) {
    end<-if(substr(current,br,br)==' ') br-1 else br
    result<-c(result,substr(current,1,end));current<-paste0(substr(current,br+1,nchar(current)),ch)
   } else {result<-c(result,current);current<-ch}
  } else current<-paste0(current,ch)
 }
 c(result,current)
}
invisible(ragg::agg_capture(width=1400,height=1400,res=300))
ordered <- do.call(rbind,lapply(groups,function(g) {
 s<-d[d$structure_group==g,];s[order(tolower(s$Name),s$inchikey,method='radix'),]
}))
wrapped <- lapply(ordered$Name,wrap)
line_counts <- vapply(wrapped,length,integer(1))
label_heights <- vapply(wrapped,function(ls) convertHeight(grobHeight(textGrob(paste(ls,collapse='\n'),
 gp=gpar(fontfamily=font,fontsize=body_size,lineheight=1.08))),'mm',valueOnly=TRUE),numeric(1))
label_widths <- vapply(wrapped,function(ls) max(vapply(ls,measure,numeric(1))),numeric(1))
grDevices::dev.off()
# Allocate angular room from text height. Group gaps are layout space, not data.
pitch <- pmax(4.9,label_heights+2.0)
group_gap <- 7.5
total_pitch <- sum(pitch)+length(groups)*group_gap
cursor <- 0
angles <- numeric(nrow(ordered));arcs <- list()
for(g in groups) {
 ids<-which(ordered$structure_group==g);start<-cursor
 for(i in ids) {angles[i]<-cursor+pitch[i]/2;cursor<-cursor+pitch[i]}
 arcs[[g]]<-c(start=start,end=cursor,mid=(start+cursor)/2)
 cursor<-cursor+group_gap
}
theta <- function(v) pi/2-v/total_pitch*2*pi
angles <- theta(angles)
ordered$angle_radians <- angles
ordered$tree_group_code <- unname(codes[ordered$structure_group])
ordered$label_lines <- line_counts
readr::write_csv(ordered,file.path(tree_data,'tree_leaves.csv'))
edges <- rbind(data.frame(parent='Level 1',child=unname(codes),kind='cohort_to_group'),
               data.frame(parent=ordered$tree_group_code,child=ordered$record_id,kind='group_to_compound'))
readr::write_csv(edges,file.path(tree_data,'tree_edges.csv'))
stopifnot(nrow(edges)==110L,setequal(ordered$inchikey,d$inchikey),!anyDuplicated(ordered$inchikey))
point <- function(r,t) c(centre+r*cos(t),centre+r*sin(t))
# Check rotated text bounding rectangles using a separating-axis intersection test.
label_polygons <- lapply(seq_len(nrow(ordered)),function(i) {
 left<-cos(angles[i])<0;rotation<-angles[i]+if(left) pi else 0
 xs<-if(left) c(-label_widths[i],0) else c(0,label_widths[i])
 corners<-rbind(c(xs[1],-label_heights[i]/2),c(xs[2],-label_heights[i]/2),
                c(xs[2],label_heights[i]/2),c(xs[1],label_heights[i]/2))
 mat<-matrix(c(cos(rotation),sin(rotation),-sin(rotation),cos(rotation)),nrow=2)
 sweep(corners %*% t(mat),2,point(label_radius,angles[i]),'+')
})
intersect <- function(a,b) {
 for(p in list(a,b)) for(k in 1:2) {
  edge<-p[k+1,]-p[k,];axis<-c(-edge[2],edge[1]);axis<-axis/sqrt(sum(axis^2))
  pa<-as.vector(a%*%axis);pb<-as.vector(b%*%axis)
  if(max(pa)<=min(pb)||max(pb)<=min(pa)) return(FALSE)
 }
 TRUE
}
collisions<-list()
for(i in 1:100) for(j in (i+1):101) if(intersect(label_polygons[[i]],label_polygons[[j]])) collisions[[length(collisions)+1]]<-c(i,j)
label_bounds<-range(unlist(label_polygons))
stopifnot(length(collisions)==0L,label_bounds[1]>2,label_bounds[2]<width_mm-2)
stroke <- function(x,y,col,lwd=1) grid.lines(x=unit(x,'mm'),y=unit(y,'mm'),gp=gpar(col=col,lwd=lwd,lineend='round'))
radial <- function(r1,r2,t,col,lwd=1) {p<-point(r1,t);q<-point(r2,t);stroke(c(p[1],q[1]),c(p[2],q[2]),col,lwd)}
arc <- function(r,from,to,col,lwd=1) {
 t<-seq(from,to,length.out=max(20,ceiling(abs(from-to)*120)))
 stroke(centre+r*cos(t),centre+r*sin(t),col,lwd)
}
disk <- function(r,t,radius,fill,col=NA,lwd=.5) {
 p<-point(r,t);grid.circle(x=unit(p[1],'mm'),y=unit(p[2],'mm'),r=unit(radius,'mm'),gp=gpar(fill=fill,col=col,lwd=lwd))
}
txt <- function(s,x,y,size=8,col='#26343D',just='centre',rot=0,face='plain') {
 grid.text(s,x=unit(x,'mm'),y=unit(y,'mm'),just=just,rot=rot,
 gp=gpar(fontfamily=font,fontsize=size,col=col,fontface=face,lineheight=1.08))
}
draw <- function() {
 grid.newpage()
 for(g in groups) {
  a<-arcs[[g]];mid<-theta(a['mid']);col<-colours[g];ids<-which(ordered$structure_group==g)
  # A shared arc forms the group branching junction, with one tip per compound.
  radial(68,91,mid,col,1.25)
  arc(91,max(angles[ids]),min(angles[ids]),col,1.25)
  arc(109,theta(a['start']),theta(a['end']),grDevices::adjustcolor(col,alpha.f=.12),8)
  for(i in ids) {
   radial(91,110,angles[i],grDevices::adjustcolor(col,alpha.f=.65),.7)
   disk(110,angles[i],.85,col)
   p<-point(label_radius,angles[i]);deg<-angles[i]*180/pi
   left<-cos(angles[i])<0
   rotate<-if(left) deg+180 else deg
   txt(paste(wrapped[[i]],collapse='\n'),p[1],p[2],body_size,
       just=if(left) 'right' else 'left',rot=rotate)
  }
  disk(78,mid,3,col)
  p<-point(78,mid);txt(codes[g],p[1],p[2],10,'white',face='bold')
 }
 # The central disk is the cohort root, with its nine group labels as a key.
 grid.circle(x=unit(centre,'mm'),y=unit(centre,'mm'),r=unit(68,'mm'),
             gp=gpar(fill='white',col='#E4E9EB',lwd=.65))
 txt('Level 1',centre,centre+47,18,face='bold')
 txt('101 compounds',centre,centre+38.5,12,col='#697780')
 for(j in seq_along(groups)) {
  g<-groups[j];y<-centre+26-(j-1)*7.3
  grid.circle(x=unit(centre-54,'mm'),y=unit(y,'mm'),r=unit(2.3,'mm'),gp=gpar(fill=colours[g],col=NA))
  txt(codes[g],centre-54,y,8.5,'white',face='bold')
  txt(report$group_labels[[g]],centre-48.5,y,10.5,just='left')
  txt(report$group_counts[[g]],centre+54,y,11.5,just='right',face='bold',col=colours[g])
 }
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_classification_tree.',fmt))
 if(fmt=='pdf') grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg') svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png') ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(sha(file.path(data_dir,'compound_identity.csv'))==input_hash)
writeLines(c('Structure-based classification tree of 101 Level 1 compounds.',
 'The central cohort connects to nine structure-based display groups (A–I), each of which connects to its member compounds. Each outer point represents one unique InChIKey; all 101 full names are shown. Group definitions and names are identical to the accompanying approved identity list. Counts appear in the central key.',
 'This is a categorical membership tree, not a molecular similarity network, clustering dendrogram or phylogeny. Branch lengths, angles and point positions do not encode risk, rank, similarity or quantitative distance. Angular spacing allows complete names to remain legible; it is not a proportional composition chart. Leaf order is alphabetical within each group.',
 'X denotes F, Cl, Br or I. The mutually exclusive assignment rules are preserved in the accompanying classification.json; the structures all regenerate their supplied InChIKeys. Original scores, ranks, Level 1 membership and the liked list figure are unchanged.',
 'The 380 x 380 mm full-name version uses 11.5 pt outer names and 10.5 pt central group labels. Long names wrap and angular spacing is reallocated to avoid overlap. Final manuscript sizing requires reflow rather than direct reduction.'),file.path(out,'captions.txt'))
outputs<-list.files(out,full.names=TRUE);outputs<-outputs[basename(outputs)!='manifest.json' & !dir.exists(outputs)]
jsonlite::write_json(list(status='review',backend='R',width_mm=380,height_mm=380,body_font_pt=body_size,
 cohort_count=101,group_count=9,edge_count=110,source_data_hash=input_hash,
 label_rectangle_overlaps=length(collisions),label_bounds_mm=label_bounds,
 group_counts=report$group_counts,source_scores_ranks_unchanged=TRUE,
 angular_spacing='text-height-aware; not quantitative',classification=report,
 script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(outputs,sha,character(1)),basename(outputs))),
 qa_notes=c('R source parses by execution','380 mm full-name review width explicitly selected',
 'Body text 11.5 pt, central labels 10.5 pt; editable vector and 600 dpi PNG; TIFF not requested')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat('Rendered 101 labelled leaves, 9 groups and 110 categorical edges.\n')
