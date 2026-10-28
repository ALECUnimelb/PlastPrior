source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
input <- file.path(repo_root,lock$files$publication$path)
stopifnot(sha256_file(input)==lock$files$publication$sha256)
compounds <- as.data.frame(readr::read_csv(input,show_col_types=FALSE))
compounds$Inchikey_std <- compounds$inchikey
stopifnot(nrow(compounds)==15125, !anyDuplicated(compounds$inchikey))
stopifnot(all(compounds$Hazard_score==floor(compounds$Hazard_score_raw+0.5)),
 all(compounds$Exposure_score==floor(compounds$Exposure_score_raw+0.5)),
 all(compounds$Priority_score==compounds$Hazard_score+compounds$Exposure_score))
compounds <- apply_figure_levels(compounds)
level_counts <- as.data.frame(table(factor(compounds$Priority_tier,levels=priority_levels)))
names(level_counts) <- c('priority_level','compound_count')
level_counts$percent <- 100*level_counts$compound_count/nrow(compounds)
stopifnot(identical(as.integer(level_counts$compound_count),as.integer(unlist(figure_policy$expected_counts))))
compounds$GIC_regulatory_status_display <- unname(regulatory_status_map[compounds$GIC_regulatory_status])
stopifnot(!anyNA(compounds$GIC_regulatory_status_display))
metadata <- list(priority_score_min=min(compounds$Priority_score),priority_score_max=max(compounds$Priority_score),priority_score_median=median(compounds$Priority_score),priority_tier_counts=as.list(table(compounds$Priority_tier)))
save_tables <- save_nested
prepared <- list(priority_score_distribution=prepare_priority_score_distribution(compounds,metadata),
 regulatory_context_inset=prepare_regulatory_context_inset(compounds),
 hazard_component_profiles=prepare_hazard_component_profiles(compounds),exposure_component_profiles=prepare_exposure_component_profiles(compounds,metadata))
for(id in names(prepared)) save_tables(prepared[[id]]$source_data,paste0(id,'/'))
grid_data <- expand.grid(Hazard_score=0:16,Exposure_score=0:16)
counts <- dplyr::count(compounds,Hazard_score,Exposure_score,name='compound_count')
grid_data <- merge(grid_data,counts,all.x=TRUE)
grid_data$compound_count[is.na(grid_data$compound_count)] <- 0L
grid_data$priority_level <- level_for(grid_data$Hazard_score,grid_data$Exposure_score)
grid_data$priority_tier <- paste('Level',grid_data$priority_level)
keys <- data.frame(priority_level=1:5,priority_tier=priority_levels,
 fill=unname(unlist(config$priority_palette)),compound_count=level_counts$compound_count)
grid_data$fill <- keys$fill[grid_data$priority_level]
stopifnot(all(tapply(grid_data$compound_count,grid_data$priority_level,sum)==level_counts$compound_count))
# WCAG relative luminance chooses the stronger of black/white text contrast.
rgb <- t(grDevices::col2rgb(grid_data$fill))/255
linear <- ifelse(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)^2.4)
lum <- as.vector(linear %*% c(.2126,.7152,.0722))
grid_data$text_colour <- ifelse((lum+.05)/.05 >= 1.05/(lum+.05),'#000000','#FFFFFF')
stopifnot(nrow(grid_data)==289,sum(grid_data$compound_count)==nrow(compounds),all(pmax((lum+.05)/.05,1.05/(lum+.05))>=4.5))
# Guide thickness: 1.15 y units x 0.4 aspect = 0.46 x units on both edges.
# Complete label boundaries: retain all 17 x 17 integer cells.
boundaries <- rbind(
 data.frame(x=c(3.5,7.5,11.5),xend=c(3.5,7.5,11.5),y=-.5,yend=16.5),
 data.frame(x=-.5,xend=16.5,y=c(3.5,7.5,11.5),yend=c(3.5,7.5,11.5)))
guides <- data.frame(label=c('L','M','H','vH'),lo=c(-.5,3.5,7.5,11.5),hi=c(3.5,7.5,11.5,16.5),fill=c('#AEB7C2','#36495D','#C88736','#A9463E'))
guides$text_colour <- c('#202830','white','#202830','white')
guides$mid <- (guides$lo+guides$hi)/2
save_tables(list(heatmap_source_data=grid_data,colour_key=keys,region_boundaries=boundaries,label_guides=guides),'hazard_exposure_landscape/')
save_tables(list(level_counts=level_counts))
save_tables(list(compound_values=compounds[,c('inchikey','Hazard_score_raw','Exposure_score_raw','Hazard_score','Exposure_score','Priority_score','Priority_level','Hazard_label','Exposure_label')]))
save_facts(list(population=nrow(compounds),level_counts=level_counts,heatmap_cells=nrow(grid_data),classification=figure_policy,scope='Figure-only five-level classification; scores, ranks and source files unchanged.'))

save_plot_data(list(prepared=prepared,grid_data=grid_data,keys=keys,boundaries=boundaries,guides=guides))
