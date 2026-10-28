#!/usr/bin/env Rscript
source('Figure/_shared/managed.R')
# Schematic-led composite; Arial, teal assembly, red hazard, green exposure.
# Values come from the current analysis; counts are descriptive, not targets.
population <- read_current(c("Inchikey_std","Priority_tier","keep_for_vega"))
counts <- as.data.frame(table(population$Priority_tier)); names(counts) <- c("Priority_tier","n")
qc <- as.data.frame(table(population$keep_for_vega)); names(qc) <- c("keep_for_vega","n")
stopifnot(nrow(population)==lock$total, sum(counts$n)==lock$total)
n <- sum(counts$n); eligible <- sum(counts$n[counts$Priority_tier!='No data'])
unknown <- n-eligible
fmt <- function(x) format(x,big.mark=',',scientific=FALSE,trim=TRUE)
nodes <- data.frame(
 x=c(rep(1,6),rep(2,5),rep(3,5)),
 y=c(9,7.55,6.10,4.65,3.20,1.55,9,7.55,5.75,4.30,2.1,9,7.25,5.5,3.6,1.65),
 label=c('Source database records','Record harmonization','Chemical identity resolution\nand structural quality control',paste0('Compound inventory\nn = ',fmt(n)),paste0('QSAR-compatible structures\nn = ',fmt(qc$n[qc$keep_for_vega=='True'])),'Other structures retained\nin the inventory',
 'PBMT hazard evidence','Persistence (2); Bioaccumulation (2)\nMobility (1); Toxicity (3)','Exposure evidence','Inventory (3); Patents (2)\nProduction (1); Literature (1)\nFood contact (1); Biomonitoring (1)','Round H and E separately\n0.5 rounds up\nMissing inputs contribute 0\nMissingness retained separately',
 'CSV + audit database','Evidence and source records\nScores and ranking',paste0('Eligible ranking\nn = ',fmt(eligible)),paste0('No data\nn = ',fmt(unknown)),'Figure priority: Levels 1–5\nH/E labels: L, M, H, vH'),
 fill=c(rep('#3C788B',6),'#B93832','#F7E4E2','#418849','#E7F0E6','#3C788B','#F0D1B5','#E8EDF0','#D9ECDD','#E9EDF1','#D9ECDD'),
 text=c(rep('white',6),'white','#192A36','white','#192A36','white',rep('#192A36',5)))
nodes$height <- .46; nodes$height[c(8,13)] <- .54
nodes$height[10] <- .75; nodes$height[11] <- .85; nodes$y[11] <- 2.0; nodes$height[16] <- .58
nodes$width <- .40
nodes$x[c(5,6)] <- c(.78,1.22); nodes$y[c(5,6)] <- 1.8; nodes$width[c(5,6)] <- .19
nodes$label[5] <- paste0('QSAR eligible\nn = ',fmt(qc$n[qc$keep_for_vega=='True']))
nodes$label[6] <- paste0('Other structures\nn = ',fmt(qc$n[qc$keep_for_vega=='False']))
nodes$x[c(14,15)] <- c(2.78,3.22); nodes$y[c(14,15)] <- 4.8; nodes$width[c(14,15)] <- .19
nodes$label[14] <- paste0('Ranked\nn = ',fmt(eligible)); nodes$label[15] <- paste0('No data\nn = ',fmt(unknown))
edges <- data.frame(x=c(1,1,1,1,1,2,2,2,2,3,3,3,2.78,3.22), xend=c(1,1,1,.78,1.22,2,2,2,2,3,2.78,3.22,3,3),
 y=c(8.52,7.07,5.62,4.17,4.17,8.52,7.07,5.27,3.82,8.52,6.77,6.77,4.32,4.32),
 end=c(8.05,6.60,5.15,2.30,2.30,8.05,6.25,4.80,2.60,7.75,5.30,5.30,2.15,2.15))
# Hazard and exposure are complementary evidence streams, not sequential analyses.
edges <- edges[-7,]
# No-evidence records are not assigned a priority level.
edges <- edges[!(edges$x==3.22 & edges$y==4.32),]
edges$end[edges$x==2 & edges$end==4.80] <- 5.15
edges$end[edges$x==2.78 & edges$end==2.15] <- 2.35
edges$y[edges$x==2 & edges$y==3.82] <- 3.45
edges$end[edges$x==2 & edges$end==2.60] <- 2.95
p <- ggplot()+
 annotate('text',x=2,y=6.63,label='+',family='Arial',size=4,colour='#264553')+
 geom_rect(data=data.frame(x=1:3),aes(xmin=x-.46,xmax=x+.46,ymin=.65,ymax=9.9),fill=NA,colour='#264553',linewidth=.5)+
 geom_segment(data=edges,aes(x=x,xend=xend,y=y,yend=end),colour='#3C788B',linewidth=.5,arrow=grid::arrow(length=grid::unit(1.6,'mm'),type='closed'))+
 geom_rect(data=nodes,aes(xmin=x-width,xmax=x+width,ymin=y-height,ymax=y+height,fill=fill),colour=NA)+
 geom_text(data=nodes,aes(x=x,y=y,label=label,colour=text),family='Arial',size=2.35,fontface='bold',lineheight=1.12)+
 annotate('text',x=1:3,y=10.28,label=c('a  Chemical space','b  Evidence and scoring','c  Results and review'),family='Arial',fontface='bold',size=2.9,hjust=.5)+
 scale_fill_identity()+scale_colour_identity()+coord_cartesian(xlim=c(.5,3.5),ylim=c(.5,10.6),expand=FALSE,clip='off')+
 theme_void(base_family='Arial')+theme(plot.background=element_rect(fill='white',colour=NA),plot.margin=margin(4,4,4,4))
save_table(nodes,'diagram_nodes');save_table(counts,'priority_population');save_table(qc,'qsar_eligibility')
save_facts(list(total=n,ranked=eligible,no_data=unknown,role='Schematic of current integer scoring and figure-only five-level classification; QSAR ineligibility does not remove compounds. The unchanged CSV and Dashboard still use four levels.',scoring_config='result/figure_data/_metadata/scoring_config.json',figure_policy=figure_policy))
save_plot(p,183,112)
