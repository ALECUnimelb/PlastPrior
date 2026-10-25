#!/usr/bin/env Rscript
source('Figure/_shared/current.R')
source(file.path(module_dir,'panels/hazard_dimension_overlap/plot.R'))
source(file.path(module_dir,'panels/exposure_dimension_overlap/plot.R'))
source(file.path(module_dir,'assemble.R'))
fields <- c('Inchikey_std',unname(hazard_score_columns),unique(unlist(exposure_score_columns)))
compounds <- read_current(fields)
for(f in setdiff(fields,'Inchikey_std')) compounds[[f]] <- strict_numeric(compounds[[f]],f)
exposure_contributions <- compounds[c('Inchikey_std',unique(unlist(exposure_score_columns)))]
raw_exposure <- exposure_contributions
for(f in setdiff(names(exposure_contributions),'Inchikey_std')) exposure_contributions[[f]][is.na(exposure_contributions[[f]])] <- 0
hazard <- prepare_hazard_overlap(compounds,file.path(output_dir,'source_data/hazard'))
exposure <- prepare_exposure_overlap(exposure_contributions,file.path(output_dir,'source_data/exposure'))
save_table(raw_exposure,'raw_exposure_scores_missing_preserved')
save_table(data.frame(Inchikey_std=compounds$Inchikey_std,exposure_complete=complete.cases(raw_exposure)),'exposure_population')
save_facts(list(hazard=hazard$statistics,exposure=exposure$statistics,full_inventory=nrow(compounds),exposure_complete=sum(complete.cases(raw_exposure)),missing='Hazard sets mean usable evidence including supported zero. Positive exposure contributions use the full inventory with missing components contributing zero. Absence of a positive contribution does not establish an observed negative; raw source missingness is exported separately.'))
save_plot(assemble_evidence_overlap_patterns(hazard$plot,exposure$plot),183,220)
