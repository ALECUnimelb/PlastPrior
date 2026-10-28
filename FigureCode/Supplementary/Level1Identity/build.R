#!/usr/bin/env Rscript
# Complete chemical-identity figure: 101 names, nine structural display groups.
# All drawing in R/grid. Arial 8.2 pt body, editable SVG/PDF, 600 dpi PNG.
# Review width_mm = 297; height fits measured text without clipping or exclusions.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root,'FigureCode/Supplementary/Level1Identity')
data_dir <- file.path(root,'result/figure_data/Level1Identity')
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1) stop('Run through FigureCode/run_retained.py')
out <- args[[1]]
dir.create(out,recursive=TRUE,showWarnings=FALSE)
source(file.path(root,'FigureCode/_shared/theme.R'))
source(file.path(root,'FigureCode/_shared/result_paths.R'))
font <- resolve_manuscript_font()
stopifnot(capabilities('cairo'))
d <- read.csv(file.path(data_dir,'compound_identity.csv'),check.names=FALSE,stringsAsFactors=FALSE)
report <- jsonlite::fromJSON(file.path(data_dir,'classification.json'))
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),all(d$inchikey==d$regenerated_inchikey))
for(p in names(report$source_hashes)) stopifnot(digest::digest(file=relocated_result_path(root,p),algo='sha256',serialize=FALSE)==report$source_hashes[[p]])
columns <- list(
 c('hal_non_aromatic','hal_heterocycle','nonhal_heterocycle'),
 c('hal_aromatic_chx','nonhal_aromatic_ch','nonhal_other'),
 c('hal_aromatic_o','hal_aromatic_ns','nonhal_o'))
stopifnot(setequal(unlist(columns),unique(d$structure_group)),!anyDuplicated(unlist(columns)))
width_mm <- 297
col_width <- 86.3
lefts <- c(10,105.3,200.6)
body_size <- 8.2
heading_size <- 9.3
ink <- '#26333C'
muted <- '#72808A'
palette <- c(hal='#3B6978',nonhal='#8C7150')
measure <- function(s,size) convertWidth(grobWidth(textGrob(s,gp=gpar(fontfamily=font,fontsize=size))),'mm',valueOnly=TRUE)
wrap <- function(s,max_width,size) {
 chars <- strsplit(s,'',fixed=TRUE)[[1]];ans<-character();current<-''
 for(ch in chars) {
  if(nzchar(current)&&measure(paste0(current,ch),size)>max_width) {
   br <- gregexpr('[ ,;-]',current)[[1]];br <- tail(br[br>0],1)
   if(length(br)&&br>nchar(current)*.45) {
    last <- if(substr(current,br,br)==' ') br-1 else br
    ans <- c(ans,substr(current,1,last));current<-paste0(substr(current,br+1,nchar(current)),ch)
   } else {ans<-c(ans,current);current<-ch}
  } else current<-paste0(current,ch)
 }
 c(ans,current)
}
prepare_layout <- function() {
 layout <- list();heights <- numeric(3)
 for(ci in 1:3) {
  y <- 10
  for(g in columns[[ci]]) {
   s <- d[d$structure_group==g,,drop=FALSE]
   s <- s[order(tolower(s$Name),s$inchikey,method='radix'),]
   label <- report$group_labels[[g]]
   hl <- wrap(label,col_width-10,heading_size)
   header_h <- length(hl)*3.7+3.2
   rows <- lapply(seq_len(nrow(s)),function(i) {
    ls <- wrap(s$Name[i],col_width-1,body_size)
    list(name=s$Name[i],lines=ls,inchikey=s$inchikey[i],record_id=s$record_id[i],height=4.6+(length(ls)-1)*3.2)
   })
   block_h <- header_h+sum(vapply(rows,function(r)r$height,numeric(1)))+5
   layout[[g]] <- list(column=ci,x=lefts[ci],top=y,header=hl,header_h=header_h,
                      count=nrow(s),rows=rows,colour=palette[if(startsWith(g,'hal_')) 'hal' else 'nonhal'])
   y <- y+block_h
  }
  heights[ci] <- y-5
 }
 list(groups=layout,height_mm=ceiling(max(heights)+9),column_heights=heights)
}
# In-memory R device resolves the same system font used by the exported PNGs.
invisible(ragg::agg_capture(width=1200,height=1200,res=300))
layout <- prepare_layout()
grDevices::dev.off()
height_mm <- layout$height_mm
rendered <- unlist(lapply(layout$groups,function(g)vapply(g$rows,function(r)r$inchikey,character(1))))
stopifnot(length(rendered)==101,!anyDuplicated(rendered),setequal(rendered,d$inchikey))
draw <- function() {
 grid.newpage()
 for(g in layout$groups) {
  y <- height_mm-g$top
  grid.lines(x=unit(c(g$x,g$x+col_width),'mm'),y=unit(c(y,y),'mm'),gp=gpar(col=g$colour,lwd=1.1))
  grid.text(paste(g$header,collapse='\n'),x=unit(g$x,'mm'),y=unit(y-2.4,'mm'),just=c('left','top'),
            gp=gpar(fontfamily=font,fontsize=heading_size,fontface='bold',col=g$colour,lineheight=1.03))
  grid.text(g$count,x=unit(g$x+col_width,'mm'),y=unit(y-2.4,'mm'),just=c('right','top'),
            gp=gpar(fontfamily=font,fontsize=heading_size,fontface='bold',col=g$colour))
  y <- y-g$header_h
  for(r in g$rows) {
   stopifnot(all(vapply(r$lines,measure,numeric(1),size=body_size)<=col_width))
   grid.text(paste(r$lines,collapse='\n'),x=unit(g$x,'mm'),y=unit(y-1.1,'mm'),just=c('left','top'),
             gp=gpar(fontfamily=font,fontsize=body_size,col=ink,lineheight=1.08))
   y <- y-r$height
  }
 }
}
for(fmt in c('pdf','svg','png','preview.png')) {
 p <- file.path(out,paste0('Level1_identity.',fmt))
 if(fmt=='pdf') grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg') svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png') ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
caption <- c(
 'Chemical identities of the 101 compounds in five-level priority Level 1.',
 'All compounds with existing integer hazard and exposure scores each >=12 are included. Groups are derived from the supplied molecular structures; every SMILES parsed successfully and regenerated the exact supplied InChIKey. Numbers in group headings are compound counts. Names are retained from the input and alphabetised within each group. The grouping and alphabetical display do not alter scores or original ranks.',
 'X denotes F, Cl, Br or I. Halogenated non-aromatics have at least one halogen atom and no aromatic atoms; this group includes cyclic structures and may contain other heteroatoms. Halogenated heteroaromatics have an aromatic non-carbon atom. The other halogenated aromatic groups are assigned in order: N/S-containing structures (possibly also containing O); O-containing structures without N/S; then C/H/X-only structures. Halogens and functional heteroatoms may occur anywhere in the molecule, not necessarily directly on an aromatic ring.',
 'Non-halogenated compounds are assigned in order to heteroaromatics, oxygen-containing compounds, C/H-only aromatic compounds, then the remaining group. The latter comprises dibenzyl disulfide, thiourea and beta-guaiene. Classification uses RDKit aromaticity perception and is a mutually exclusive display scheme for this cohort, not a comprehensive chemical ontology or an inferred function in plastics.',
 'Full identifiers, CAS numbers, input SMILES, original use annotations, structure flags, scores and ranks are provided in the accompanying source-data CSV. No food-contact, biomonitoring, score-distribution or regulatory panel is included in this identity figure.',
 sprintf('Review layout: %.0f x %.0f mm; body text %.1f pt. This wide full-name proof is not intended to be reduced to a journal double-column width without reflow.',width_mm,height_mm,body_size)
)
writeLines(caption,file.path(out,'captions.txt'))
sha <- function(p) digest::digest(file=p,algo='sha256',serialize=FALSE)
outputs <- list.files(out,full.names=TRUE);outputs<-outputs[basename(outputs)!='manifest.json' & !dir.exists(outputs)]
manifest <- list(status='review',backend='R',width_mm=width_mm,height_mm=height_mm,
 font=font,body_font_pt=body_size,cohort_count=101,rendered_unique_names=101,
 group_counts=report$group_counts,classification=report,source_scores_ranks_unchanged=TRUE,
 column_heights=layout$column_heights,
 display_order=lapply(layout$groups,function(g)vapply(g$rows,function(r)r$record_id,character(1))),
 script_hashes=as.list(setNames(vapply(file.path(module,c('build.R','prepare.py')),sha,character(1)),c('build.R','prepare.py'))),
 output_hashes=as.list(setNames(vapply(outputs,sha,character(1)),basename(outputs))),
 source_data_hash=sha(file.path(data_dir,'compound_identity.csv')),
 static_preflight_notes=c('R parse verified by execution; wide review layout explicitly selected',
 'Body font explicitly set to 8.2 pt and headings to 9.3 pt; line widths checked on each output device',
 'TIFF omitted from review; editable PDF/SVG and 600 dpi PNG supplied'))
jsonlite::write_json(manifest,file.path(out,'manifest.json'),pretty=TRUE,auto_unbox=TRUE)
cat(sprintf('Rendered all 101 names in nine groups, %.0f x %.0f mm.\n',width_mm,height_mm))
