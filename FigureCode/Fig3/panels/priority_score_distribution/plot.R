plot_priority_score_distribution <- function(panel_data,config,variant='publication') {
 d <- panel_data$priority_distribution
 d$Priority_tier <- factor(d$Priority_tier,levels=priority_levels)
 totals <- aggregate(compound_count~score_bin,d,sum)
 ggplot(d,aes(score_bin,compound_count,fill=Priority_tier))+
 geom_col(width=.82,colour='white',linewidth=.15)+
 scale_fill_manual(values=named_palette(config,'priority_palette'),breaks=priority_levels)+
 scale_x_continuous(breaks=seq(0,32,2),expand=expansion(add=.55))+
 scale_y_continuous(labels=scales::comma,limits=c(0,max(totals$compound_count)*1.65),expand=expansion(mult=c(0,0)))+
 geom_text(data=totals,aes(score_bin,compound_count,label=scales::comma(compound_count)),inherit.aes=FALSE,vjust=-.4,size=2,check_overlap=TRUE)+
 labs(x='Priority score (rounded H + rounded E)',y='Number of compounds')+
 priority_landscape_theme()+theme(legend.position='top',legend.justification='left')
}
