stop("This experimental export is retired. Use the current figure entrypoints in Figure/INDEX.md.")
#!/usr/bin/env Rscript
# Three descriptive composition panels. No scoring or ranking calculations.
# Review canvas: width_mm = 320, height_mm = 245; Arial 11.5 pt labels.
suppressPackageStartupMessages(library(grid))
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
source(file.path(root,'Figure/_shared/result_paths.R'))
module <- file.path(root,'Figure/Level1Composition')
out <- file.path(root,'result/figures',basename(module),'images')
data_out <- file.path(root,'result/figures/Level1Composition/review/data')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
dir.create(data_out,recursive=TRUE,showWarnings=FALSE)
source(file.path(root,'Figure/_shared/theme.R'))
font <- if(tolower(resolve_manuscript_font())=='arial') 'Arial' else 'sans'
sha <- function(p) digest::digest(file=p,algo='sha256',serialize=FALSE)
identity_path <- file.path(root,'result/figures/Level1Identity/review/data/compound_identity.csv')
classification_path <- file.path(root,'result/figures/Level1Identity/review/data/classification.json')
full_path <- file.path(root,'result/PlastPrior_results.csv')
protected <- c(identity_path,classification_path,full_path,unlist(lapply(
 c('Level1Evidence','Level1Identity','Level1IdentityTree','Level1UseMatrix','Level1UseTreemap'),
 function(m) list.files(file.path(root,'result/figures',m,'images'),full.names=TRUE))))
before <- setNames(vapply(protected,sha,character(1)),protected)
d <- as.data.frame(readr::read_csv(identity_path,show_col_types=FALSE))
full <- as.data.frame(readr::read_csv(full_path,show_col_types=FALSE))
classification <- jsonlite::fromJSON(classification_path)
for(p in names(classification$source_hashes))
 stopifnot(sha(relocated_result_path(root,p))==classification$source_hashes[[p]])
idx <- match(d$inchikey,full$inchikey)
stopifnot(nrow(d)==101L,!anyDuplicated(d$inchikey),!anyNA(idx),all(d$Figure_priority_level==1),
 setequal(d$inchikey,full$inchikey[full$Hazard_score>=12 & full$Exposure_score>=12]))
for(f in c('Name','CAS','SMILES','Hazard_score','Exposure_score','Priority_score','Priority_rank','Top_n_selected'))
 stopifnot(identical(as.character(d[[f]]),as.character(full[[f]][idx])))
d$GIC_regulatory_status <- full$GIC_regulatory_status[idx]

counts <- function(v) {x<-as.data.frame(table(v),stringsAsFactors=FALSE);names(x)<-c('category','n');x}
use <- counts(d$primary_use)
use <- use[order(-use$n,use$category,method='radix'),]
use_labels <- c('Chemical intermediate or reagent'='Intermediate / reagent',
 'Pesticide or biocide'='Pesticide / biocide','Polymer starting material'='Polymer starting material',
 'Solvent'='Solvent','Flame retardant'='Flame retardant',
 'Contaminant or transformation product'='Contaminant /\ntransformation product',
 'Nutritional or cosmetic ingredient'='Nutritional /\ncosmetic ingredient',
 'Heat transfer fluid or refrigerant'='Heat-transfer fluid /\nrefrigerant',
 'Other industrial use'='Other industrial use',
 'Polymerization or curing agent'='Polymerization /\ncuring agent',
 'Corrosion inhibitor'='Corrosion inhibitor','Fuel additive'='Fuel additive',
 'Lubricant additive'='Lubricant additive','Natural fragrance constituent'='Natural fragrance constituent',
 'Optical material or colorant'='Optical material / colorant','Polymer processing aid'='Polymer processing aid')
use$label <- unname(use_labels[use$category])
structure_order <- c('hal_non_aromatic','hal_aromatic_chx','hal_aromatic_o','hal_aromatic_ns',
 'hal_heterocycle','nonhal_aromatic_ch','nonhal_o','nonhal_heterocycle','nonhal_other')
structure_labels <- c('Halogenated non-aromatics','Halogenated aromatics:\nC/H/X only',
 'Halogenated aromatics:\noxygen-containing','Halogenated aromatics:\nnitrogen / sulfur-containing',
 'Halogenated heteroaromatics','Aromatic hydrocarbons',
 'Non-halogenated\noxygen compounds','Non-halogenated\nheteroaromatics','Other non-halogenated\ncompounds')
structure <- counts(d$structure_group)
structure <- structure[match(structure_order,structure$category),]
structure$label <- structure_labels
reg_order <- c('prohibited_or_phaseout','restricted_or_authorisation_required','candidate_or_high_concern',
 'monitoring_reporting_or_hazard_classification','inventory_registration_or_use_only')
reg <- counts(d$GIC_regulatory_status)
stopifnot(setequal(reg$category,reg_order))
reg <- reg[match(reg_order,reg$category),]
reg$label <- c('Prohibited / phase-out','Restricted / authorisation','Candidate / high concern',
 'Monitoring / reporting /\nhazard classification','Inventory / registration / use')
stopifnot(nrow(use)==16,nrow(structure)==9,nrow(reg)==5,
 all(vapply(list(use,structure,reg),function(x)sum(x$n),numeric(1))==101),!anyNA(use$label))
for(nm in c('use','structure','reg')) readr::write_csv(get(nm),file.path(data_out,paste0(nm,'_counts.csv')))
readr::write_csv(d,file.path(data_out,'compound_membership.csv'))

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
for(fmt in c('pdf','svg','png','preview.png')) {
 p<-file.path(out,paste0('Level1_composition.',fmt))
 if(fmt=='pdf') grDevices::cairo_pdf(p,width=width_mm/25.4,height=height_mm/25.4,family=font)
 else if(fmt=='svg') svglite::svglite(p,width=width_mm/25.4,height=height_mm/25.4)
 else if(fmt=='png') ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=600,background='white')
 else ragg::agg_png(p,width=width_mm,height=height_mm,units='mm',res=300,background='white')
 tryCatch(draw(),finally=grDevices::dev.off())
}
stopifnot(identical(before,setNames(vapply(protected,sha,character(1)),protected)))
writeLines(c('Composition of the 101 Level 1 compounds.',
 'a, Counts by primary use. Each compound retains one user-supplied primary-use assignment. b, Counts by the nine mutually exclusive structure-based display groups used in the classification tree. The ordered classification rules are retained in the source classification report; these are descriptive groups, not a comprehensive chemical ontology. X denotes F, Cl, Br or I. c, Counts by GIC regulatory annotation in the source database; these annotations do not constitute a current jurisdiction-specific legal review.',
 'All three panels include the same 101 unique InChIKeys selected by the five-level Level 1 definition. Bars give compound counts, with explicit zero-based axes and independent panel ranges. No observations or categories were excluded. General primary-use annotations are not asserted to be specific functions in plastics.',
 'Existing scores, ranks and Top-n membership are preserved. No uncertainty intervals or statistical tests apply to these descriptive counts. Plot size is 320 x 245 mm with 11.5 pt category text and 13.5 pt headings; review proof, not final manuscript sizing.'),file.path(module,'caption.txt'))
outputs<-list.files(out,full.names=TRUE);outputs<-outputs[basename(outputs)!='manifest.json']
jsonlite::write_json(list(status='review',backend='R',cohort=101,panels=c(16,9,5),
 width_mm=width_mm,height_mm=height_mm,label_font_pt=11.5,excluded_rows=0,
 scores_ranks_unchanged=TRUE,previous_figures_unchanged=TRUE,
 protected_hashes=as.list(before),script_sha256=sha(file.path(module,'build.R')),
 output_hashes=as.list(setNames(vapply(outputs,sha,character(1)),basename(outputs))),
 qa_notes=c('320 mm review width to retain large labels; reflow needed for manuscript sizing',
 'Actual R execution verifies parsing; font sizes set in the grid helper',
 'PDF/SVG and 600 dpi PNG provided; TIFF not requested',
 'Source-data GIC annotations only; no new legal interpretation')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
cat('Three-panel sample exported: 101 compounds in every panel; source data and existing figures unchanged.\n')
