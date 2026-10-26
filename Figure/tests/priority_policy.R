# Regression checks for strict and inclusive boundaries, independent of display bins.
source('Figure/_shared/priority_policy.R')
config <- list(thresholds=list(moderate_hazard_min=6,high_hazard_gt=10,exposure_min=5))
h <- c(0,5.99,6,9.75,10,10.01,10,10.01,16)
e <- c(0,5,5,5,5,5,4.99,4.99,10)
expected <- c('Low priority','Low priority','Moderate priority','Moderate priority','Moderate priority','High priority','Low priority','Moderate priority','High priority')
stopifnot(identical(derive_priority_tier_shared(h+e,h,e,config),expected))
# Different total scores never substitute for the H/E boundaries.
stopifnot(identical(derive_priority_tier_shared(c(16,16,16),c(5.5,10,11),c(10.5,6,5),config),c('Low priority','Moderate priority','High priority')))
for (cutoff in c(9,11)) {
 h <- c(cutoff-.01,cutoff,cutoff+.01,cutoff+.01)
 e <- c(5,5,5,4.99)
 stopifnot(identical(derive_priority_tier_shared(h+e,h,e,config,high_hazard_gt=cutoff),c('Moderate priority','Moderate priority','High priority','Moderate priority')))
}
stopifnot(derive_priority_tier_shared(0,0,0,config,statuses='No data')=='No data')
lock <- jsonlite::fromJSON('Figure/figure_sources.json')
d <- read.csv(lock$files$publication$path,check.names=FALSE)
stopifnot(all(derive_priority_tier_shared(d$Priority_score,d$Hazard_score,d$Exposure_score,config)==d$Priority_tier))
cat('R policy boundaries and all',nrow(d),'formal classifications passed.\n')
