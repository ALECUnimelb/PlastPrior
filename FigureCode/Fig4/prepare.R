source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
identity_dir <- file.path(repo_root,'result/figure_data/Level1Identity')
d <- as.data.frame(readr::read_csv(file.path(identity_dir,'compound_identity.csv'),show_col_types=FALSE))
full <- as.data.frame(readr::read_csv(file.path(repo_root,lock$files$publication$path),show_col_types=FALSE))
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
for(nm in c('use','structure','reg')) save_table(get(nm),paste0(nm,'_counts'))
save_table(d,'compound_membership')
file.copy(file.path(identity_dir,c('compound_identity.csv','classification.json')),file.path(output_dir,'source_data'),overwrite=TRUE)
file.copy(file.path(repo_root,'result/figure_data/_dependencies/Level1_101_aligned_uses_en.csv'),file.path(output_dir,'source_data/primary_use_annotations.csv'),overwrite=TRUE)
save_facts(list(cohort=101,panels=c(16,9,5),scores_ranks_unchanged=TRUE))

save_plot_data(list(use=use,structure=structure,reg=reg))
