"""Generate replacement SI tables from the same locked analysis and figures."""
from pathlib import Path
import json,sqlite3,shutil
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];lock=json.loads((ROOT/'FigureCode/figure_sources.json').read_text());out=ROOT/'result/figure_data/SupplementaryTables';out.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(ROOT/lock['files']['analysis']['path']) as db:
 f=pd.read_sql_query('SELECT inchikey,Priority_tier,Hazard_available_dimensions,Analytical_detectability FROM compounds',db)
tiers=['Low priority','Moderate priority','High priority'];rows=[];coverage=[];platforms=[]
for tier in tiers+['All compounds']:
 x=f if tier=='All compounds' else f[f.Priority_tier.eq(tier)];n=len(x);counts=pd.to_numeric(x.Hazard_available_dimensions).value_counts()
 rows.append({'Tier':tier,'n':n,**{str(i)+' domains':f'{int(counts.get(i,0)):,} ({100*counts.get(i,0)/n:.1f}%)' for i in range(5)}})
 matched=~x.Analytical_detectability.eq('No NORMAN SusDat match');resolved=x.Analytical_detectability.isin(['GC-EI','RPLC +ESI','RPLC -ESI'])
 coverage.append({'Tier':tier,'n':n,'Matched':f'{matched.sum():,} ({100*matched.mean():.1f}%)','Resolved':f'{resolved.sum():,} ({100*resolved.mean():.1f}%)','Matched unresolved':int((matched&~resolved).sum()),'No match':int((~matched).sum())})
 platforms.append({'Tier':tier,**{v:f'{x.Analytical_detectability.eq(v).sum():,} ({100*x.Analytical_detectability.eq(v).mean():.1f}%)' for v in ['GC-EI','RPLC +ESI','RPLC -ESI']}})
for name,data in [('Table_S7',rows),('Table_S12a',coverage),('Table_S12b',platforms)]:pd.DataFrame(data).to_csv(out/(name+'.csv'),index=False)
for n in ['Table_S8','Table_S9','Table_S10']:shutil.copyfile(ROOT/'result/figure_data/_dependencies/baseline/supplementary/adi'/(n+'.csv'),out/(n+'.csv'))
parts=[]
for file,kind in [('leave_one_input_out/leave_one_input_out.csv','Delete'),('scenario_sensitivity/scenario_sensitivity.csv','Scenario')]:
 x=pd.read_csv(ROOT/'result/figure_data/_dependencies/baseline/figure_data/Fig4'/file)
 for row in x.to_dict('records'):
  parts.append({'Analysis':'Delete: '+row['component'] if kind=='Delete' else row['scenario'],'rank_rho':row['rank_spearman'],'tier_agreement':row['tier_agreement'],'High_retention':row['high_priority_retention'],'High_Jaccard':row['high_priority_jaccard'],'High_n':row['perturbed_high_count']})
pd.DataFrame(parts).to_csv(out/'Table_S11.csv',index=False)
# Formatted text is a reading aid; CSV retains full-precision values.
lines=['# Replacement supplementary tables','Source run: '+lock['run_id'],'']
for name in ['Table_S7','Table_S8','Table_S9','Table_S10','Table_S11','Table_S12a','Table_S12b']:
 x=pd.read_csv(out/(name+'.csv'),keep_default_na=False)
 for col in x:
  if col in ['rank_rho']:x[col]=x[col].map(lambda v:f'{v:.3f}')
  if col in ['tier_agreement','High_retention','High_Jaccard']:x[col]=x[col].map(lambda v:f'{100*v:.1f}%')
 lines+=['## '+name,'','| '+' | '.join(x.columns)+' |','| '+' | '.join(['---']*len(x.columns))+' |']+['| '+' | '.join(map(str,row))+' |' for row in x.itertuples(index=False,name=None)]+['']
(out/'replacement_tables.md').write_text('\n'.join(lines)+'\n')
print(out)
