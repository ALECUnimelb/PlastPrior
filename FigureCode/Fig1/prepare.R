source('FigureCode/_shared/managed.R')
source(file.path(module_dir,'setup.R'))
population <- read_current(c("Inchikey_std","Priority_tier","keep_for_vega"))
counts <- as.data.frame(table(population$Priority_tier)); names(counts) <- c("Priority_tier","n")
qc <- as.data.frame(table(population$keep_for_vega)); names(qc) <- c("keep_for_vega","n")
stopifnot(nrow(population)==lock$total, sum(counts$n)==lock$total)
n <- sum(counts$n); eligible <- sum(counts$n[counts$Priority_tier!='No data'])
unknown <- n-eligible
save_table(counts,'priority_population');save_table(qc,'qsar_eligibility')
save_facts(list(total=n,ranked=eligible,no_data=unknown,role='Schematic of current integer scoring and figure-only five-level classification; QSAR ineligibility does not remove compounds. The unchanged CSV and Dashboard still use four levels.',scoring_config='result/figure_data/_metadata/scoring_config.json',figure_policy=figure_policy))

save_plot_data(list(counts=counts,qc=qc,n=n,eligible=eligible,unknown=unknown))
