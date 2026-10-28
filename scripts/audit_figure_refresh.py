"""Independently audit formal data, figure bins, perturbations and Dashboard tiers."""
from pathlib import Path
import collections,csv,hashlib,json,math,statistics,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'audit_archive/figure_refresh_20261026'
LOCK=json.loads((ROOT/'FigureCode/figure_sources.json').read_text())
DATA=ROOT/LOCK['figure_data_dir']
def rows(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def number(r,k):return float(r[k]) if r[k] else 0.0
def classify(h,e,cutoff=10):
 return 'High priority' if h>cutoff and e>=5 else 'Moderate priority' if (6<=h<=cutoff and e>=5) or (h>cutoff and e<5) else 'Low priority'
def close(a,b):assert math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-10),(a,b)
def rank(values):
 ordered=sorted(enumerate(values),key=lambda x:x[1]);out=[0.0]*len(values);start=0
 while start<len(ordered):
  end=start+1
  while end<len(ordered) and ordered[end][1]==ordered[start][1]:end+=1
  for idx,_ in ordered[start:end]:out[idx]=(start+end+1)/2
  start=end
 return out
r=rows(ROOT/LOCK['files']['publication']['path']);n=len(r)
assert n==15125 and len({x['inchikey'] for x in r})==n
for x in r:assert classify(number(x,'Hazard_score'),number(x,'Exposure_score'))==x['Priority_tier']
counts=dict(collections.Counter(x['Priority_tier'] for x in r));assert counts==LOCK['population']
# Byte-identical formal files protect all raw scores, evidence, ranks and Top-N fields.
before=json.loads((AUDIT/'before.json').read_text())
for path,digest in before['formal_files'].items():assert sha(ROOT/path)==digest,path
baseline=rows(ROOT/'audit_archive/20261025T202848Z-3408a32e/package/PlastPrior_results.csv')
baseline={x['inchikey']:x for x in baseline}
for x in r:
 for k in ['Hazard_score','Exposure_score','Priority_score','Priority_rank','Ranking_eligible','Top_n_selected']:
  assert x[k]==baseline[x['inchikey']][k],(x['inchikey'],k)
top=[x['inchikey'] for x in r if x['Top_n_selected'].lower()=='true'];assert len(top)==100
# Fig. 3 histograms and approved heatmap must conserve identities and counts.
expected=collections.Counter((math.floor(number(x,'Priority_score')),x['Priority_tier']) for x in r)
actual={(int(x['score_bin']),x['Priority_tier']):int(x['compound_count']) for x in rows(DATA/'Fig3/priority_score_distribution/priority_distribution.csv')}
assert all(actual.get(k,0)==v for k,v in expected.items()) and sum(actual.values())==n
old_heights=collections.Counter(math.floor(number(x,'Priority_score')) for x in baseline.values())
assert old_heights==collections.Counter(math.floor(number(x,'Priority_score')) for x in r)
heat=rows(DATA/'Fig3/hazard_exposure_landscape/heatmap_source_data.csv')
assert len(heat)==187 and sum(int(x['compound_count']) for x in heat)==n
approved=rows(AUDIT/'approved_heatmap_counts.csv')
key=lambda x:(int(x['hazard_position']),int(x['exposure_bin']))
assert {key(x):(int(x['compound_count']),x['priority'],x['fill_colour']) for x in heat}=={key(x):(int(x['compound_count']),x['priority'],x['fill_colour']) for x in approved}
assert all(x['fill_colour'].startswith('#') and float(x['text_contrast'])>=4.5 for x in heat)
assign=rows(DATA/'Fig3/hazard_exposure_landscape/compound_bin_assignments.csv');lookup={x['inchikey']:x for x in r}
assert len(assign)==n and len({x['Inchikey_std'] for x in assign})==n
for x in assign:
 original=lookup[x['Inchikey_std']];h=number(original,'Hazard_score');e=number(original,'Exposure_score')
 assert int(x['hazard_position'])==(11 if 10<h<11 else math.floor(h)) and int(x['exposure_bin'])==math.floor(e)
 assert x['Priority_tier']==original['Priority_tier']
# Independent perturbation arithmetic and set membership.
h=[number(x,'Hazard_score') for x in r];e=[number(x,'Exposure_score') for x in r];score=[a+b for a,b in zip(h,e)]
tiers=[x['Priority_tier'] for x in r];base_high={i for i,t in enumerate(tiers) if t=='High priority'}
def scenario(sid):
 hh=h.copy();ee=e.copy();cutoff=10
 for i,x in enumerate(r):
  inv=number(x,'Exposure_inventory_score')
  if sid=='equal_pbmt_weights':hh[i]=2*sum(number(x,k+'_score') for k in ['Persistence','Bioaccumulation','Mobility','Toxicity'])
  elif sid=='inventory_linear':ee[i]=e[i]-inv+min(.5*number(x,'Exposure_inventory_listing_count'),2)
  elif sid=='inventory_halved':ee[i]=e[i]-.5*inv
  elif sid=='exposure_capped':ee[i]=min(e[i],8)
 if sid=='high_hazard_gt_9':cutoff=9
 elif sid=='high_hazard_gt_11':cutoff=11
 return hh,ee,cutoff
rank_base=rank(score)
def metrics(hh,ee,cutoff=10):
 tt=[classify(a,b,cutoff) for a,b in zip(hh,ee)];high={i for i,t in enumerate(tt) if t=='High priority'}
 return {'rank_spearman':statistics.correlation(rank_base,rank([a+b for a,b in zip(hh,ee)])),
 'tier_agreement':sum(a==b for a,b in zip(tt,tiers))/n,
 'high_priority_retention':len(high&base_high)/len(base_high),
 'high_priority_jaccard':len(high&base_high)/len(high|base_high),
 'changed_tier_count':sum(a!=b for a,b in zip(tt,tiers)), 'perturbed_high_count':len(high)},high
scenario_table=rows(DATA/'Fig4/scenario_sensitivity/scenario_sensitivity.csv');stable=base_high.copy()
for row in scenario_table:
 sid=row['scenario_id'];hh,ee,cutoff=scenario(sid);m,high=metrics(hh,ee,cutoff)
 for k,v in m.items():close(row[k],v)
 if sid in ['equal_pbmt_weights','inventory_linear','inventory_halved','exposure_capped']:stable&=high
config=json.loads((ROOT/'FigureCode/_shared/sensitivity/figure.yml').read_text())
leave={x['component']:x for x in rows(DATA/'Fig4/leave_one_input_out/leave_one_input_out.csv')}
for c in config['components']:
 removed=[number(x,c['score_column'])*c['multiplier'] for x in r]
 hh=[a-v if c['family']=='Hazard' else a for a,v in zip(h,removed)]
 ee=[a-v if c['family']=='Exposure' else a for a,v in zip(e,removed)]
 m,high=metrics(hh,ee)
 for k,v in m.items():close(leave[c['component']][k],v)
 close(leave[c['component']]['retained_high_count'],len(high&base_high))
summary=json.loads((ROOT/'result/figure_data/_metadata/Fig5/caption_facts.json').read_text())
assert len(stable)==summary['stable_high_priority_count']==125
policy_rows=rows(DATA/'Fig5/compound_policy_analysis.csv')
assert {x['Inchikey_std'] for x in policy_rows if x['stable_high_priority'].lower()=='true'}=={r[i]['inchikey'] for i in stable}
strong={'prohibited_or_phaseout','restricted_or_authorisation_required','candidate_or_high_concern'}
outside={i for i in stable if r[i]['GIC_regulatory_status'] not in strong}
assert len(outside)==summary['stable_outside_strong_action_count']==62
assert sum(r[i]['GIC_regulatory_status']=='not_listed' for i in outside)==1
# Run the actual Dashboard classifier on every formal record, not just the screenshot compound.
dashboard_root=Path(os.environ.get('PLASTPRIOR_DASHBOARD_ROOT',ROOT/'audit_archive/dashboard_runtime_20261026')).resolve()
js="""import fs from 'node:fs';
const {getPriorityScoreLevel,getPriorityScore}=await import(process.env.PLASTPRIOR_PRIORITY_MODULE);
const rows=JSON.parse(fs.readFileSync(0,'utf8')); const names={high:'High priority',medium:'Moderate priority',low:'Low priority'};
for(const row of rows) { const before=JSON.stringify(row); if(names[getPriorityScoreLevel(row)]!==row.Priority_tier) throw new Error('Tier mismatch: '+row.inchikey); if(getPriorityScore(row)!==Number(row.Priority_score))throw new Error('Score mismatch');if(JSON.stringify(row)!==before)throw new Error('Source mutated');}
console.log('Dashboard: '+rows.length+' records match formal scores and tiers.');"""
fields=['inchikey','Hazard_score','Exposure_score','Priority_score','Priority_tier','Priority_data_status','Ranking_eligible','priority_scoring_policy']
result=subprocess.run(['node','--input-type=module','-e',js],input=json.dumps([{k:x[k] for k in fields} for x in r]),text=True,cwd=ROOT,capture_output=True,check=True,env={**os.environ,'PLASTPRIOR_PRIORITY_MODULE':(dashboard_root/'app/src/core/priorityScore.js').as_uri()})
# Data unaffected by the tier policy must regenerate identically.
unchanged=[]
for path,digest in before['figure_data_hashes'].items():
 p=Path(path);fig=p.parts[1];rel=Path(*p.parts[4:]);now=DATA/fig/rel
 if fig=='Fig1' and str(rel)=='priority_population.csv':
  assert {x['Priority_tier']:int(x['n']) for x in rows(now)}==counts
 elif fig in ['Fig1','Fig2','ExtendedDataFig1','ExtendedDataFig2']:
  assert now.exists() and sha(now)==digest,str(now);unchanged.append(str(now.relative_to(ROOT)))
report={'run_id':LOCK['run_id'],'population':n,'priority_counts':counts,'formal_files_unchanged':True,'raw_scores_ranks_top100_unchanged_vs_previous_policy':True,'top100_count':len(top),'heatmap_cells':len(heat),'heatmap_zero_cells':sum(int(x['compound_count'])==0 for x in heat),'approved_heatmap_counts_colours_identical':True,'histogram_bin_heights_unchanged':True,'fig4_independent_scenarios':len(scenario_table),'fig4_independent_ablations':len(leave),'fig5_stable_high':len(stable),'fig5_stable_outside_strong_action':len(outside),'dashboard':result.stdout.strip(),'unchanged_source_tables':len(unchanged)}
(AUDIT/'data_verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
