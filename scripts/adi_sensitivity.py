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
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from rdkit import rdBase
from plastprior import hazard as pm, hazard_bt as bt, priority

H=['Persistence_score','Bioaccumulation_score','Mobility_score','Toxicity_score']

def classify(h,e):
    """Use the canonical policy on unrounded domain sums, without a total gate."""
    if len(h) != len(e):
        raise ValueError('Hazard and exposure populations differ.')
    return np.asarray([priority.tier(hazard, exposure) for hazard, exposure in zip(h, e)])


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.database=a.database.resolve(strict=True);a.output=a.output.resolve()
    if a.output.exists() and (not a.output.is_dir() or any(a.output.iterdir())):
        p.error('Output must be a new or empty directory; existing analyses are not overwritten.')
    source_hash=sha256(a.database);source_run_id=None
    fields=list(dict.fromkeys(['inchikey','qsar_smiles','db_extract_info','qsar_identity_status','qsar_identity_reason','qsar_evidence_available','lrtp_available',*pm.INPUT_FIELDS,*bt.MODEL_FIELDS,*H,'Exposure_score','Hazard_score','Priority_score','Priority_tier']))
    if a.database.suffix=='.csv':
        data=pd.read_csv(a.database,usecols=fields,dtype=str,keep_default_na=False).sort_values('inchikey').reset_index(drop=True)
    else:
      with sqlite3.connect(a.database.as_uri()+'?mode=ro',uri=True) as db:
        data=pd.read_sql_query('SELECT '+','.join('"'+c.replace('"','""')+'"' for c in fields)+' FROM compounds ORDER BY inchikey',db).fillna('')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_metadata'").fetchone():
            row=db.execute("SELECT value_json FROM run_metadata WHERE key='run_id'").fetchone()
            source_run_id=json.loads(row[0]) if row else None
    if data.inchikey.eq('').any() or data.inchikey.duplicated().any():
        raise ValueError('Compound keys must be nonempty and unique.')
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
        h=scores.fillna(0).mul([priority.POLICY['hazard_weights'][c] for c in H],axis=1).sum(axis=1);total=h+exposure;tier=pd.Series(classify(h,exposure))
        if not np.isfinite(pd.concat([h,exposure,total])).all():
            raise ValueError('Domain sums and totals must be finite.')
        if cutoff==.5:
            pd.testing.assert_frame_equal(scores,baseline,check_dtype=False)
            assert np.array_equal(h,pd.to_numeric(data.Hazard_score)) and np.array_equal(total,baseline_score) and tier.equals(base_tier),'Baseline mismatch'
        new_high=tier.eq('High priority');inter=int((high&new_high).sum());union=int((high|new_high).sum())
        # Pearson correlation of average ranks equals Spearman, including ties.
        rho=float(total.rank(method='average').corr(baseline_score.rank(method='average')))
        summaries.append({'ADI':cutoff,'High_n':int(new_high.sum()),'rank_rho':rho,'tier_agreement':float((tier==base_tier).mean()),'High_retention':inter/int(high.sum()) if high.any() else None,'High_Jaccard':inter/union if union else None,'changed_tier_n':int((tier!=base_tier).sum())})
        availability.append({'ADI':cutoff,**{c:int(scores[c].notna().sum()) for c in H},'all_four':int(scores.notna().all(axis=1).sum()),'none':int(scores.isna().all(axis=1).sum())})
        for (old,new),n in pd.DataFrame({'old':base_tier,'new':tier}).value_counts().items():
            if old!=new:transitions.append({'ADI':cutoff,'baseline_tier':old,'scenario_tier':new,'n':int(n)})
        pd.concat([data[['inchikey']],scores,pd.DataFrame({'H':h,'E':exposure,'S':total,'tier':tier})],axis=1).to_csv(a.output/f'ADI_{cutoff:.2f}_compound_scores.csv',index=False)
    for name,rows in [('Table_S8',summaries),('Table_S9',availability),('Table_S10',transitions)]:pd.DataFrame(rows).to_csv(a.output/(name+'.csv'),index=False)
    if sha256(a.database)!=source_hash:
        raise RuntimeError('Source changed during sensitivity analysis.')
    for row in summaries:
        assert sum(t['n'] for t in transitions if t['ADI']==row['ADI'])==row['changed_tier_n'], 'Transition totals mismatch'
    root=Path(__file__).resolve().parents[1]
    code_paths=[Path(__file__),Path(pm.__file__),Path(bt.__file__),Path(priority.__file__)]
    policy_paths=[root/'plastprior'/name for name in ['priority_policy.json','hazard_policy.json','hazard_bt_policy.json']]
    report={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source':{'path':str(a.database),'sha256':source_hash,'run_id':source_run_id},'source_unchanged':True,'priority_policy_version':priority.POLICY['policy_version'],'policy_sha256':{str(path.relative_to(root)):sha256(path) for path in policy_paths},'code_sha256':{str(path.relative_to(root)):sha256(path) for path in code_paths},'baseline_exact_reproduction':True,'baseline_checks':['full compound population','PBMT values and missingness','H','E held fixed','S','priority tiers'],'n':len(data),'thresholds':[.5,.65,.8,.85],'fixed':'exposure, admitted identities, LRTP outputs, Ames without ADI, fallback rules and weights','summary':summaries,'availability':availability,'off_diagonal_transitions':transitions,'outputs_sha256':{path.name:sha256(path) for path in sorted(a.output.glob('*.csv'))}}
    (a.output/'ADI_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
