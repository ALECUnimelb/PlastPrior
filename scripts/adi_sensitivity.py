"""Recalculate PBMT ADI sensitivity with fixed admitted evidence and exposure.

Runs canonical candidate-selection functions; independently checks baseline,
aggregation and metrics. Never relaxes identity or source-admission gates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from rdkit import rdBase
from plastprior import hazard as pm, hazard_bt as bt

H=['Persistence_score','Bioaccumulation_score','Mobility_score','Toxicity_score']

def classify(h,e):
    return np.where((h+e>=12)&(h>=4)&(e>=4),'High priority',np.where((h+e>=6)&(h>=2)&(e>=2),'Moderate priority','Low priority'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    fields=list(dict.fromkeys(['inchikey','qsar_smiles','db_extract_info','qsar_identity_status','qsar_identity_reason','qsar_evidence_available','lrtp_available',*pm.INPUT_FIELDS,*bt.MODEL_FIELDS,*H,'Exposure_score','Hazard_score','Priority_score','Priority_tier']))
    if a.database.suffix=='.csv':
        data=pd.read_csv(a.database,usecols=fields,dtype=str,keep_default_na=False).sort_values('inchikey').reset_index(drop=True)
    else:
      with sqlite3.connect(a.database.as_uri()+'?mode=ro',uri=True) as db:
        data=pd.read_sql_query('SELECT '+','.join('"'+c.replace('"','""')+'"' for c in fields)+' FROM compounds ORDER BY inchikey',db).fillna('')
    p_inputs=pm.scoring_inputs(data);b_inputs=bt.scoring_inputs(data)
    baseline=data[H].apply(pd.to_numeric,errors='coerce');exposure=pd.to_numeric(data.Exposure_score);baseline_score=pd.to_numeric(data.Priority_score)
    base_tier=data.Priority_tier;high=base_tier.eq('High priority');summaries=[];availability=[];transitions=[]
    a.output.mkdir(parents=True,exist_ok=True)
    for cutoff in [.5,.65,.8,.85]:
        print('ADI',cutoff,flush=True)
        pf=pm.add_persistence_columns(p_inputs.copy(),adi_threshold=cutoff)
        pf=pm.add_mobility_columns(pf,adi_threshold=cutoff)
        with rdBase.BlockLogs(): bf=bt.add_bioaccumulation_columns(b_inputs.copy(),adi_threshold=cutoff,show_progress=False)
        bf=bt.add_toxicity_columns(bf,adi_threshold=cutoff,show_progress=False)
        scores=pd.concat([pf[['Persistence_score','Mobility_score']],bf[['Bioaccumulation_score','Toxicity_score']]],axis=1)[H].apply(pd.to_numeric,errors='coerce')
        h=scores.fillna(0).mul([2,2,1,3],axis=1).sum(axis=1);total=h+exposure;tier=pd.Series(classify(h,exposure))
        if cutoff==.5:
            pd.testing.assert_frame_equal(scores,baseline,check_dtype=False)
            assert np.array_equal(h,pd.to_numeric(data.Hazard_score)) and np.array_equal(total,baseline_score) and tier.equals(base_tier),'Baseline mismatch'
        new_high=tier.eq('High priority');inter=int((high&new_high).sum());union=int((high|new_high).sum())
        # Pearson correlation of average ranks equals Spearman, including ties.
        rho=float(total.rank(method='average').corr(baseline_score.rank(method='average')))
        summaries.append({'ADI':cutoff,'High_n':int(new_high.sum()),'rank_rho':rho,'tier_agreement':float((tier==base_tier).mean()),'High_retention':inter/int(high.sum()),'High_Jaccard':inter/union,'changed_tier_n':int((tier!=base_tier).sum())})
        availability.append({'ADI':cutoff,**{c:int(scores[c].notna().sum()) for c in H},'all_four':int(scores.notna().all(axis=1).sum()),'none':int(scores.isna().all(axis=1).sum())})
        for (old,new),n in pd.DataFrame({'old':base_tier,'new':tier}).value_counts().items():
            if old!=new:transitions.append({'ADI':cutoff,'baseline_tier':old,'scenario_tier':new,'n':int(n)})
        pd.concat([data[['inchikey']],scores,pd.DataFrame({'H':h,'E':exposure,'S':total,'tier':tier})],axis=1).to_csv(a.output/f'ADI_{cutoff:.2f}_compound_scores.csv',index=False)
    for name,rows in [('Table_S8',summaries),('Table_S9',availability),('Table_S10',transitions)]:pd.DataFrame(rows).to_csv(a.output/(name+'.csv'),index=False)
    report={'baseline_exact_reproduction':True,'n':len(data),'thresholds':[.5,.65,.8,.85],'fixed':'exposure, admitted identities, LRTP outputs, Ames without ADI, fallback rules and weights','summary':summaries,'availability':availability}
    (a.output/'ADI_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
