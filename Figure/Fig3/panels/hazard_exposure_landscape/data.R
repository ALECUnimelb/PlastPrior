prepare_hazard_exposure_landscape <- function(compounds, metadata, config) {
 d <- compounds
 stopifnot(nrow(d)==lock$total, !anyDuplicated(d$Inchikey_std),
           all(is.finite(d$Hazard_score)),all(is.finite(d$Exposure_score)),
           all(d$Hazard_score>=0 & d$Hazard_score<=16),
           all(d$Exposure_score>=0 & d$Exposure_score<=10))
 classify <- function(h,e) derive_priority_tier_shared(h+e,h,e,config)
 stopifnot(all(d$Priority_tier==classify(d$Hazard_score,d$Exposure_score)))
# Display bins preserve the raw-score classification across strict thresholds.
hazard_position <- function(h) ifelse(h>10 & h<11,11,floor(h))
d$hazard_position <- hazard_position(d$Hazard_score)
d$exposure_bin <- floor(d$Exposure_score)
x_labels <- as.character(0:16)
x_intervals <- c(paste0(0:9,' <= H < ',1:10),'H = 10','10 < H < 12',paste0(12:15,' <= H < ',13:16),'H = 16')
d$hazard_interval <- x_intervals[d$hazard_position+1]
counts <- d |> dplyr::group_by(hazard_position,exposure_bin) |> dplyr::summarise(compound_count=dplyr::n(),tier_count=dplyr::n_distinct(Priority_tier),priority=dplyr::first(Priority_tier),.groups='drop')
stopifnot(all(counts$tier_count==1),sum(counts$compound_count)==nrow(d))
grid <- merge(expand.grid(hazard_position=0:16,exposure_bin=0:10),counts,by=c('hazard_position','exposure_bin'),all.x=TRUE)
grid$compound_count[is.na(grid$compound_count)] <- 0L
# Empty cells inherit the priority region; compound classifications are unchanged.
empty <- grid$compound_count==0L
grid$priority[empty] <- classify(grid$hazard_position[empty],grid$exposure_bin[empty])
grid$hazard_interval <- x_intervals[grid$hazard_position+1]
grid$exposure_interval <- ifelse(grid$exposure_bin==10,'E = 10',paste0(grid$exposure_bin,' <= E < ',grid$exposure_bin+1))
priority_levels <- c('Low priority','Moderate priority','High priority')
count_labels <- c('0–10','11–50','51–100','>100')
grid$count_band <- cut(grid$compound_count,breaks=c(0,10,50,100,Inf),labels=count_labels,ordered_result=TRUE,include.lowest=TRUE)
# Opaque shades retain visible colour for small positive counts.
palettes <- list('Low priority'=c('#8C9FAF','#687F93','#476279','#293F55'),
                 'Moderate priority'=c('#E2AE65','#CD8D39','#A96920','#79450D'),
                 'High priority'=c('#D1837C','#BD5D55','#9C3D36','#702721'))
key <- expand.grid(count_band=count_labels,priority=priority_levels,stringsAsFactors=FALSE)
key$colour <- mapply(function(p,b) palettes[[p]][match(b,count_labels)],key$priority,key$count_band)
key$x <- match(key$count_band,count_labels)
key$y <- 4-match(key$priority,priority_levels)
key$join_key <- paste(key$priority,key$count_band)
grid$fill_colour <- key$colour[match(paste(grid$priority,grid$count_band),key$join_key)]
stopifnot(!anyNA(grid$fill_colour))
# Pick black or white from relative luminance of each final opaque colour.
luminance <- function(colours) {
 rgb <- t(col2rgb(colours))/255
 linear <- ifelse(rgb<=0.04045,rgb/12.92,((rgb+0.055)/1.055)^2.4)
 as.vector(linear %*% c(.2126,.7152,.0722))
}
lum <- luminance(grid$fill_colour)
grid$text_colour <- ifelse((lum+.05)/.05 >= 1.05/(lum+.05),'#000000','#FFFFFF')
grid$text_contrast <- pmax((lum+.05)/.05,1.05/(lum+.05))
stopifnot(min(grid$text_contrast)>=4.5)
 expected <- unlist(lock$population)
 actual <- table(factor(d$Priority_tier,levels=names(expected)))
 stopifnot(all(actual==expected),nrow(grid)==187)
 list(source_data=list(heatmap_source_data=grid,colour_key=key,
   compound_bin_assignments=d[c('Inchikey_std','Hazard_score','Exposure_score','Priority_score','Priority_tier','hazard_position','hazard_interval','exposure_bin')]),
   statistics=list(population_plotted=nrow(d),occupied_cells=sum(grid$compound_count>0),total_cells=nrow(grid),
     mixed_priority_cells=0,minimum_text_contrast=min(grid$text_contrast),
     tier_counts=as.list(actual),raw_scores_unchanged=TRUE,
     display_bins='Floor H/E except 10<H<11 maps to H bin 11. H bin 10 contains H=10 only; bin 11 spans 10<H<12. Endpoint bins H=16 and E=10 are singletons.',
     encoding='Equal categorical cells; priority hue and four count bands: 0-10,11-50,51-100,>100. Exact counts include zero.'))
}
