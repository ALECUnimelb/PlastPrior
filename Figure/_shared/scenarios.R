# Deliberate sensitivity perturbations of the same baseline population and zero-contribution rule.
# Both Fig. 4 and Fig. 5 use this implementation; baseline scores are unmodified.
score_scenario <- function(id, hazard, exposure, raw_scores, inventory, inventory_count) {
  if(any(!is.finite(c(hazard,exposure,inventory,inventory_count,unlist(raw_scores))))) stop('Scenario requires finite contributions; retain missingness in the source table.')
  h <- hazard; e <- exposure
  if(id=='equal_pbmt_weights') h <- 2*(raw_scores[['Persistence']]+raw_scores[['Bioaccumulation']]+raw_scores[['Mobility']]+raw_scores[['Toxicity']])
  else if(id=='inventory_linear') e <- exposure-inventory+pmin(.5*inventory_count,2)
  else if(id=='inventory_halved') e <- exposure-.5*inventory
  else if(id=='exposure_capped') e <- pmin(exposure,8)
  else if(!id %in% c('baseline','high_threshold_11','high_threshold_13')) stop('Unknown scenario: ',id)
  list(score=h+e,hazard=h,exposure=e)
}
