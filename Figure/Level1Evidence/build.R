stop("This experimental export is retired. Use the current figure entrypoints in Figure/INDEX.md.")
#!/usr/bin/env Rscript
# Figure contract: quantitative grid; complete five-level Level 1 cohort.
# Claim: identify all 101 dual-vH compounds and describe their uses and evidence.
# R-only drawing and export. New layouts; existing manuscript font conventions.
# Overview: width_mm = 183, height_mm = 210. Evidence: 260 x 225 mm review plates.
# Arial, editable SVG/PDF; ragg PNG at 600 dpi, R-rendered previews at 300 dpi.
# No rescore, rerank, imputation, clustering, inferential tests, or row exclusions.
suppressPackageStartupMessages({library(ggplot2); library(grid)})
root <- '/Users/ruiwang/Projects/APPs/PlastPrior'
module <- file.path(root, 'Figure/Level1Evidence')
out <- file.path(root,'result/figures',basename(module),'images')
data_out <- file.path(root, 'result/figures/Level1Evidence/review/data')
dir.create(out, recursive=TRUE, showWarnings=FALSE)
dir.create(data_out, recursive=TRUE, showWarnings=FALSE)
source(file.path(root, 'Figure/_shared/theme.R'))
font <- resolve_manuscript_font()
stopifnot(capabilities('cairo'))
for (p in c('readr','jsonlite','digest','ragg','svglite')) stopifnot(requireNamespace(p, quietly=TRUE))
sha <- function(p) digest::digest(file=p, algo='sha256', serialize=FALSE)
write_json <- function(x,p) jsonlite::write_json(x,p,auto_unbox=TRUE,pretty=TRUE,na='null')
input_path <- file.path(module, 'inputs/Level1_101_aligned_uses_en.csv')
result_path <- file.path(root, 'result/PlastPrior_results.csv')
policy_path <- file.path(root, 'Figure/_shared/five_level_policy.json')
config_path <- file.path(root, 'result/scoring_config.json')
lock <- jsonlite::fromJSON(file.path(root,'Figure/managed_sources.json'))
source_paths <- c(input_path,result_path,policy_path,config_path)
hashes_before <- setNames(vapply(source_paths,sha,character(1)),source_paths)
stopifnot(sha(result_path)==lock$files$publication$sha256)
u <- as.data.frame(readr::read_csv(input_path, col_types=readr::cols(.default=readr::col_character())))
d <- as.data.frame(readr::read_csv(result_path, show_col_types=FALSE))
policy <- jsonlite::fromJSON(policy_path)
config <- jsonlite::fromJSON(config_path)
stopifnot(nrow(u)==101L, !anyDuplicated(u$inchikey), !anyDuplicated(d$inchikey), nrow(d)==15125L,
          !anyNA(u), all(nzchar(as.matrix(u))))
level_matrix <- policy$level_matrix_L_M_H_vH
figure_levels <- level_matrix[cbind(findInterval(d$Hazard_score,policy$cutpoints)+1L,
                                     findInterval(d$Exposure_score,policy$cutpoints)+1L)]
stopifnot(identical(as.integer(table(factor(figure_levels,levels=1:5))), as.integer(policy$expected_counts)),
          setequal(u$inchikey,d$inchikey[figure_levels==1L]))
idx <- match(u$inchikey,d$inchikey)
stopifnot(!anyNA(idx), identical(u$Name,d$Name[idx]), identical(u$CAS,d$CAS[idx]))
cohort <- cbind(u, d[idx,setdiff(names(d),names(u)),drop=FALSE])
cohort$Source_priority_level <- cohort$Priority_level
cohort$Figure_priority_level <- figure_levels[idx]
cohort <- cohort[order(-cohort$Priority_score,cohort$inchikey),]
rownames(cohort) <- NULL
cohort$Display_order <- seq_len(nrow(cohort))
cohort$Evidence_page <- rep(1:3,c(34,34,33))
stopifnot(all(cohort$Figure_priority_level==1L), all(cohort$Hazard_score>=12),
          all(cohort$Exposure_score>=12), all(cohort$Priority_score==cohort$Hazard_score+cohort$Exposure_score))
score_fields <- c('Hazard_score','Exposure_score','Priority_score','Priority_rank','Top_n_selected')
for(f in score_fields) stopifnot(identical(cohort[[f]],d[[f]][match(cohort$inchikey,d$inchikey)]))

use_counts <- as.data.frame(table(cohort$primary_use),stringsAsFactors=FALSE)
names(use_counts) <- c('primary_use','compound_count')
use_counts <- use_counts[order(-use_counts$compound_count,use_counts$primary_use),]
use_counts$percent <- 100*use_counts$compound_count/101
use_short <- c('Chemical intermediate or reagent'='Intermediate / reagent',
 'Pesticide or biocide'='Pesticide / biocide','Polymer starting material'='Polymer starting material',
 'Solvent'='Solvent','Flame retardant'='Flame retardant',
 'Contaminant or transformation product'='Contaminant / transformation product',
 'Nutritional or cosmetic ingredient'='Nutritional / cosmetic ingredient',
 'Heat transfer fluid or refrigerant'='Heat-transfer fluid / refrigerant',
 'Polymerization or curing agent'='Polymerization / curing agent',
 'Other industrial use'='Other industrial use','Polymer processing aid'='Polymer processing aid',
 'Fuel additive'='Fuel additive','Optical material or colorant'='Optical material / colorant',
 'Corrosion inhibitor'='Corrosion inhibitor','Lubricant additive'='Lubricant additive',
 'Natural fragrance constituent'='Natural fragrance constituent')
stopifnot(setequal(names(use_short),unique(cohort$primary_use)))
reg_codes <- c('prohibited_or_phaseout'='A','restricted_or_authorisation_required'='B',
 'candidate_or_high_concern'='C','monitoring_reporting_or_hazard_classification'='D',
 'inventory_registration_or_use_only'='E')
reg_names <- c(A='Prohibited / phase-out', B='Restricted / authorisation', C='Candidate / high concern',
 D='Monitoring / reporting / hazard', E='Inventory / registration / use')
reg_colours <- c(A='#54366E',B='#786086',C='#A28EAE',D='#CEC3D4',E='#EAE5ED')
cohort$Regulatory_code <- unname(reg_codes[cohort$GIC_regulatory_status])
stopifnot(!anyNA(cohort$Regulatory_code))
reg_counts <- data.frame(code=names(reg_names),label=unname(reg_names),
 compound_count=as.integer(table(factor(cohort$Regulatory_code,levels=names(reg_names)))))
evidence_use <- do.call(rbind,lapply(use_counts$primary_use,function(use) {
 s <- cohort[cohort$primary_use==use,,drop=FALSE]
 do.call(rbind,lapply(c('Food contact','Human biomonitoring'),function(indicator) {
  field <- if(indicator=='Food contact') 'Exposure_food_contact_score' else 'Exposure_human_biomonitoring_score'
  v <- s[[field]]
  data.frame(primary_use=use,indicator=indicator,total=nrow(s),positive=sum(v>0,na.rm=TRUE),
             available=sum(!is.na(v)),missing=sum(is.na(v)))
 }))
}))
evidence_use$fraction <- evidence_use$positive/evidence_use$available
stopifnot(sum(reg_counts$compound_count)==101L,sum(use_counts$compound_count)==101L,
          sum(evidence_use$positive[evidence_use$indicator=='Food contact'])==58,
          sum(evidence_use$positive[evidence_use$indicator=='Human biomonitoring'])==16,
          all(evidence_use$total==evidence_use$available+evidence_use$missing))
component_fields <- c('Persistence_score','Mobility_score','Bioaccumulation_score','Toxicity_score',
 'Exposure_food_contact_score','Exposure_human_biomonitoring_score','Exposure_inventory_score',
 'Exposure_production_score','Exposure_patent_score','Exposure_literature_score')
component_labels <- c('P','M','B','T','FC','HB','Inv','Prd','Pat','Lit')
weights <- c(2,1,2,3,1,1,3,1,2,1)
stopifnot(identical(as.numeric(c(unlist(config$hazard_weights[component_fields[1:4]]),
                               unlist(config$exposure_weights[component_fields[5:10]]))),weights))
cm <- as.matrix(cohort[,component_fields])
stopifnot(all(is.na(cm)|cm %in% c(0,0.5,1,2)))
coverage <- data.frame(component=component_fields,positive=colSums(cm>0,na.rm=TRUE),
 zero=colSums(cm==0,na.rm=TRUE),missing=colSums(is.na(cm)))
readr::write_csv(cohort,file.path(data_out,'compound_evidence.csv'),na='')
readr::write_csv(use_counts,file.path(data_out,'use_counts.csv'))
readr::write_csv(reg_counts,file.path(data_out,'regulatory_counts.csv'))
readr::write_csv(evidence_use,file.path(data_out,'evidence_by_use.csv'))
obsolete_table <- file.path(data_out,'hazard_exposure_counts.csv')
if(file.exists(obsolete_table)) unlink(obsolete_table)
readr::write_csv(coverage,file.path(data_out,'component_coverage.csv'))
readr::write_csv(data.frame(primary_use=names(use_short),display_label=unname(use_short)),file.path(data_out,'use_display_labels.csv'))

ink <- '#263440'; muted <- '#69747D'; teal <- '#326F78'; warm <- '#9D5149'
theme_set(theme_manuscript(7.5,font))
use_counts$label <- factor(unname(use_short[use_counts$primary_use]),levels=rev(unname(use_short[use_counts$primary_use])))
use_plot <- ggplot(use_counts,aes(compound_count,label))+
 geom_col(width=.57,fill=teal)+geom_text(aes(label=compound_count),hjust=-.5,size=2.5,family=font,colour=ink)+
 scale_y_discrete(labels=function(z) vapply(z,function(v) paste(strwrap(v,29),collapse='\n'),character(1)))+
 scale_x_continuous(limits=c(0,31),breaks=c(0,10,20,30),expand=c(0,0))+
 labs(x='Number of compounds',y=NULL)+
 theme(axis.line.y=element_blank(),axis.ticks.y=element_blank(),axis.text.y=element_text(size=7.1),
       plot.margin=margin(2,6,3,0),axis.title.x=element_text(size=7.3))
evidence_use$label <- factor(unname(use_short[evidence_use$primary_use]),levels=levels(use_counts$label))
evidence_use$indicator <- factor(evidence_use$indicator,levels=c('Food contact','Human biomonitoring'))
evidence_use$cell_label <- paste0(evidence_use$positive,'/',evidence_use$available,
                                ifelse(evidence_use$missing>0,'*',''))
evidence_use_plot <- ggplot(evidence_use,aes(indicator,label))+
 geom_tile(aes(fill=fraction),width=.86,height=.57)+
 geom_text(aes(label=cell_label,colour=fraction>=.8),size=2.5,family=font)+
 scale_fill_gradient(low='#F1F5F5',high=teal,limits=c(0,1),guide='none')+
 scale_colour_manual(values=c('FALSE'=ink,'TRUE'='white'),guide='none')+
 scale_x_discrete(labels=c('Food\ncontact','Human\nbiomonitoring'),expand=expansion(add=.6))+
 scale_y_discrete(drop=FALSE)+labs(x=NULL,y=NULL)+
 theme(axis.line=element_blank(),axis.ticks=element_blank(),axis.text.y=element_blank(),
       axis.text.x=element_text(size=7.3),plot.margin=margin(2,0,3,0))
reg_counts$label <- factor(reg_counts$label,levels=rev(reg_counts$label))
reg_plot <- ggplot(reg_counts,aes(factor(code,levels=names(reg_names)),compound_count,fill=code))+
 geom_col(width=.6)+geom_text(aes(label=compound_count),vjust=-.5,size=2.5,family=font,colour=ink)+
 scale_fill_manual(values=reg_colours,guide='none')+
 scale_x_discrete(labels=function(z) vapply(unname(reg_names[z]),function(v) paste(strwrap(v,22),collapse='\n'),character(1)))+
 scale_y_continuous(limits=c(0,52),breaks=c(0,20,40),expand=c(0,0))+labs(x=NULL,y='Number of compounds')+
 theme(axis.line.x=element_blank(),axis.ticks.x=element_blank(),axis.text.x=element_text(size=7),
       plot.margin=margin(2,2,3,0),axis.title.y=element_text(size=7.2))

# Use physical dimensions for consistent typography and exact row alignment.
tx <- function(label,x,y,size=7.2,col=ink,face='plain',just='left',rot=0) {
 grid.text(label,x=unit(x,'mm'),y=unit(y,'mm'),just=just,rot=rot,
           gp=gpar(fontfamily=font,fontsize=size,col=col,fontface=face,lineheight=1.0))
}
rect <- function(x,y,w,h,fill,col=NA,lwd=.3) grid.rect(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm'),gp=gpar(fill=fill,col=col,lwd=lwd))
line <- function(x1,y1,x2,y2,col='#DBE1E5',lwd=.45) grid.lines(x=unit(c(x1,x2),'mm'),y=unit(c(y1,y2),'mm'),gp=gpar(col=col,lwd=lwd))
draw_plot <- function(p,x,y,w,h) {
 pushViewport(viewport(x=unit(x,'mm'),y=unit(y,'mm'),width=unit(w,'mm'),height=unit(h,'mm')))
 grid.draw(if(inherits(p,'ggplot')) ggplotGrob(p) else p);popViewport()
}
draw_overview <- function() {
 grid.newpage()
 tx('a',8,203,9,face='bold');tx('Primary uses',13,203,8.6,face='bold')
 tx('b',119,203,9,face='bold');tx('Evidence by use',124,203,8.6,face='bold')
 left <- ggplotGrob(use_plot);right <- ggplotGrob(evidence_use_plot)
 stopifnot(length(left$heights)==length(right$heights))
 common_heights <- unit.pmax(left$heights,right$heights)
 left$heights <- right$heights <- common_heights
 draw_plot(left,59,134,105,128)
 draw_plot(right,147,134,58,128)
 tx('Positive / available',147,67,6.8,col=muted,just='centre')
 tx('c',8,58,9,face='bold');tx('GIC regulatory annotations',13,58,8.6,face='bold')
 draw_plot(reg_plot,92,29,168,51)
}

# Fit all labels to measured physical widths; never truncate compound names.
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
component_x <- c(184,189,194,199,207,212,217,222,227,232)
score_fill <- c('0'='#FFFFFF','0.5'='#DDEBEC','1'='#A6C9CD','2'='#326F78')
layout_audits <- list()
draw_evidence <- function(page) {
 grid.newpage()
 pushViewport(viewport(x=unit(0,'mm'),y=unit(-16,'mm'),width=unit(260,'mm'),height=unit(225,'mm'),just=c('left','bottom')))
 s <- cohort[cohort$Evidence_page==page,,drop=FALSE]
 tx(sprintf('%d / 3',page),251,238,7,just='right',col=muted)
 tx('IDENTITY AND PRIMARY USE',9,234,7.1,col=muted,face='bold')
 tx('EXISTING SCORES',153.5,234,7.1,col=muted,face='bold',just='centre')
 tx('HAZARD',191.5,234,7.1,col=warm,face='bold',just='centre')
 tx('EXPOSURE',219.5,234,7.1,col=teal,face='bold',just='centre')
 tx('GIC',245,234,7.1,col=muted,face='bold',just='centre')
 tx('ID',9,227,7,face='bold');tx('Compound',21,227,7,face='bold');tx('CAS',91,227,7,face='bold');tx('Primary use',115,227,7,face='bold')
 for(j in seq_along(c('H','E','Total','Rank'))) tx(c('H','E','Total','Rank')[j],c(152,159,167,176)[j],227,7,face='bold',just='centre')
 for(j in seq_along(component_x)) {tx(component_labels[j],component_x[j],227,6.6,face='bold',just='centre');tx(paste0('x',weights[j]),component_x[j],222.8,6.1,col=muted,just='centre')}
 tx('Code',245,227,6.8,face='bold',just='centre')
 line(9,220,251,220,col=ink,lwd=.6)
 name_lines <- use_lines <- numeric(nrow(s));max_widths <- numeric(nrow(s))
 for(i in seq_len(nrow(s))) {
  y <- 216.6-(i-1)*5.35
  if(i %% 2L==0L) rect(130,y,242,5.35,'#F7F9FA')
  name <- wrap_measured(s$Name[i],67,7.4)
  use <- wrap_measured(unname(use_short[s$primary_use[i]]),32,6.9)
  name_lines[i] <- length(strsplit(name,'\n')[[1]]);use_lines[i] <- length(strsplit(use,'\n')[[1]])
  stopifnot(name_lines[i]<=2L,use_lines[i]<=2L)
  tx(sub('L1_','',s$record_id[i]),9,y,6.8,col=muted)
  tx(name,21,y,7.4);tx(s$CAS[i],91,y,7.1,col=muted);tx(use,115,y,6.9)
  rect(152,y,5.6,4.15,'#F2E4E1');rect(159,y,5.6,4.15,'#E5EFF0')
  tx(s$Hazard_score[i],152,y,7.2,col=warm,face='bold',just='centre')
  tx(s$Exposure_score[i],159,y,7.2,col=teal,face='bold',just='centre')
  tx(s$Priority_score[i],167,y,7.3,face='bold',just='centre')
  tx(s$Priority_rank[i],176,y,6.8,col=muted,just='centre')
  for(j in seq_along(component_x)) {
   v <- s[[component_fields[j]]][i]
   fill <- if(is.na(v)) '#E3E6E9' else unname(score_fill[as.character(v)])
   rect(component_x[j],y,4.3,4.15,fill,col=if(is.na(v)) '#B8C0C6' else '#D1DCDD')
   tx(if(is.na(v)) 'NA' else as.character(v),component_x[j],y,6.1,
      col=if(!is.na(v)&&v==2) 'white' else ink,just='centre')
  }
  code <- s$Regulatory_code[i]
  rect(245,y,5.3,4.15,reg_colours[code])
  tx(code,245,y,6.8,col=if(code %in% c('A','B')) 'white' else ink,face='bold',just='centre')
 }
 line(9,34,251,34)
 tx('Component tiles: unweighted scores',9,29,7.2,face='bold')
 for(j in seq_along(score_fill)) {
  x <- 69+(j-1)*12;v<-names(score_fill)[j]
  rect(x,29,4,3.8,score_fill[j],col='#C5D2D4');tx(v,x+3,29,6.7)
 }
 rect(118,29,4,3.8,'#E3E6E9',col='#B8C0C6');tx('NA = missing',121,29,6.7)
 popViewport()
 layout_audits[[paste0('page_',page)]] <<- list(rows=nrow(s),max_name_lines=max(name_lines),max_use_lines=max(use_lines),
     row_pitch_mm=5.35,min_font_pt=6.1,name_font_pt=7.4,width_mm=260,height_mm=225)
}
export_draw <- function(draw,stem,width_mm,height_mm) {
 for(fmt in c('pdf','svg','png','preview.png')) {
  f <- file.path(out,paste0(stem,'.',fmt))
  if(fmt=='pdf') grDevices::cairo_pdf(f,width=width_mm/25.4,height=height_mm/25.4,family=font)
  else if(fmt=='svg') svglite::svglite(f,width=width_mm/25.4,height=height_mm/25.4)
  else if(fmt=='png') ragg::agg_png(f,width=width_mm,height=height_mm,units='mm',res=600,background='white')
  else ragg::agg_png(f,width=width_mm,height=height_mm,units='mm',res=300,background='white')
  tryCatch(draw(),finally=grDevices::dev.off())
 }
}
export_draw(draw_overview,'Level1_overview',183,210)
for(page in 1:3) export_draw(function() draw_evidence(page),paste0('Level1_evidence_page',page),260,225)
grDevices::cairo_pdf(file.path(out,'Level1_evidence_101.pdf'),width=260/25.4,height=225/25.4,family=font)
tryCatch(for(page in 1:3) draw_evidence(page),finally=grDevices::dev.off())
hashes_after <- setNames(vapply(source_paths,sha,character(1)),source_paths)
stopifnot(identical(hashes_before,hashes_after),identical(as.integer(table(cohort$Evidence_page)),c(34L,34L,33L)))
caption <- c(
 'Overview | Uses, food-contact and human biomonitoring evidence, and regulatory annotations of 101 Level 1 compounds.',
 'a, Counts by user-supplied primary use (one category per compound; detailed uses may overlap). b, Rows align with the use categories in a. Each cell gives the number of compounds with a positive food-contact or human-biomonitoring indicator divided by the number with an available indicator; colour encodes that fraction (0 to 1). An asterisk marks a denominator reduced by missing evidence: human biomonitoring is available for 21 of 22 pesticide/biocide compounds. All 101 compounds and all 16 uses remain represented. These are database evidence indicators, not measured concentrations, exposure magnitudes, or occurrence rates in people. c, Counts by GIC regulatory annotation category in the source database.',
 'Evidence atlas | Complete five-level Level 1 cohort, displayed over three pages (34, 34 and 33 compounds). Compound identity, primary use, existing H/E/total scores, original all-compound competition ranks, four hazard components, six exposure indicators and GIC category are shown. Rows are ordered by existing total score descending, then InChIKey ascending within ties. Row IDs retain the supplied identifier and are not ranks. Shortened use labels map to the full source labels in the source-data table.',
 'Tiles show unweighted component scores, with weighting factors in the column headers. H and E are the existing rounded weighted domain totals; they are not recalculated from tiles. FC and HB have a maximum score of 1; other component scores have a maximum of 2. NA indicates missing evidence and is distinct from a score of 0. Detailed use labels are retained in the source-data table.',
 'Abbreviations: P, persistence; M, mobility; B, bioaccumulation; T, toxicity; FC, food contact; HB, human biomonitoring; Inv, inventory; Prd, production; Pat, patent; Lit, literature. GIC codes: A, prohibited/phase-out; B, restricted/authorisation; C, candidate/high concern; D, monitoring/reporting/hazard classification; E, inventory/registration/use.',
 'Cohort definition: five-level figure policy, H >=12 and E >=12, n=101 of 15,125 compounds. Source CSV classification remains four-level and is retained separately in source data. These 101 compounds are not a Top-101 ranking; 93 belong to the existing Top-100 selection including boundary ties, which contains 159 compounds overall.',
 'The unit is a unique InChIKey. These panels provide descriptive counts and scores, with no replicate measurements, error bars, hypothesis tests, or causal claims. GIC annotations reflect the source database and do not constitute current jurisdiction-specific legal determinations. Primary/detailed uses are user-supplied annotations and have not been independently source-verified.',
 'Review dimensions: overview 183 x 210 mm; evidence plates 260 x 225 mm, intentionally wider to retain readable complete chemical names. Overall titles and narrative footnotes are in this separate caption rather than embedded in the figures.'
)
writeLines(caption,file.path(module,'captions.txt'))
facts <- list(cohort=101,total=15125,five_level_counts=as.integer(table(figure_levels)),
 input_unique=TRUE,exact_set_match=TRUE,identity_name_cas_match=TRUE,source_hashes_unchanged=TRUE,
 scores_and_ranks_identical=TRUE,excluded_rows=0,pages=c(34,34,33),
 top_n_in_cohort=sum(cohort$Top_n_selected),top_n_in_population=sum(d$Top_n_selected),
 component_missing=as.list(setNames(colSums(is.na(cm)),component_labels)),layout=layout_audits,
 overview_panel_b=list(kind='positive/available indicators by primary use',use_categories=16,
    food_contact_positive=58,food_contact_available=101,human_biomonitoring_positive=16,
    human_biomonitoring_available=100,missing_denominator_marked=TRUE),
 backend='R',font=font,review_status='Draft for user review; not promoted into manuscript figures',
 static_preflight_notes=c('Actual R parse succeeds; delimiter-only checker requests R syntax confirmation',
 'TIFF omitted for this review: editable PDF/SVG and 600 dpi PNG provided; previews are 300 dpi'),
 classification='five-level Level 1; source classification preserved separately',
 limitations=c('User-supplied use annotations lack row-level citations','GIC annotations are database context, not a current legal review',
               'Evidence plates are wide review figures; final journal layout not established'))
write_json(facts,file.path(out,'qa.json'))
outputs <- list.files(out,full.names=TRUE)
outputs <- outputs[basename(outputs)!='manifest.json']
manifest <- list(status='review',run_id=lock$run_id,backend=R.version.string,
 sources=as.list(hashes_before),script_sha256=sha(file.path(module,'build.R')),
 files=as.list(setNames(vapply(outputs,sha,character(1)),basename(outputs))),
 source_data=as.list(setNames(vapply(list.files(data_out,full.names=TRUE),sha,character(1)),list.files(data_out))),
 facts=facts)
write_json(manifest,file.path(out,'manifest.json'))
cat('Created overview + three evidence pages; 101/101 identities verified; source scores and ranks unchanged.\n')
