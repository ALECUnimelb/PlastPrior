"""Independent full-population check of the approved scoring-policy migration.

Does not import production scoring, ranking, or policy code. All assertions must
pass before the report is written. Raw component values remain missing.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import pandas as pd

HAZARD = ['Persistence_score', 'Bioaccumulation_score', 'Mobility_score', 'Toxicity_score']
EXPOSURE = ['Exposure_' + x + '_score' for x in ['food_contact','human_biomonitoring','inventory','production','patent','literature']]

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def read(db, table):
    return pd.read_sql_query('SELECT * FROM '+table+' ORDER BY inchikey', db).fillna('').set_index('inchikey')

def number(x):
    return None if x is None or str(x).strip()=='' else Decimal(str(x))

def table_hash(db, table):
    h=hashlib.sha256(); n=0
    for row in db.execute('SELECT * FROM '+table+' ORDER BY 1'):
        h.update((json.dumps(row,ensure_ascii=False,default=str)+'\n').encode()); n+=1
    return {'rows':n,'sha256':h.hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with sqlite3.connect(args.candidate.as_uri()+'?mode=ro',uri=True) as db, sqlite3.connect(args.baseline.as_uri()+'?mode=ro',uri=True) as old_db:
        current=read(db,'compounds');old=read(old_db,'compounds');history=read(db,'historical_results')
        assert current.index.equals(old.index) and current.index.equals(history.index)
        # Verify evidence identity, not just final score equality.
        unchanged=HAZARD+EXPOSURE+[c for c in current if c.endswith('_available') or c.endswith('_unavailable_reason')]+['qsar_identity_status','gic_name_review_required','db_extract_info','Persistence_evidence','Mobility_evidence','Bioaccumulation_evidence','Toxicity_evidence']
        for col in unchanged:
            assert current[col].equals(old[col]), 'Unexpected upstream change: '+col
        provenance={t:table_hash(db,t) for t in ['source_records','compound_memberships','historical_results']}
        for t,data in provenance.items(): assert data==table_hash(old_db,t), 'Source or historical table changed: '+t
        scores={};rows=[]
        for key,row in current.iterrows():
            hvals=[number(row[c]) for c in HAZARD];evals=[number(row[c]) for c in EXPOSURE]
            h=sum((x or 0)*w for x,w in zip(hvals,[2,2,1,3]));e=sum(x or 0 for x in evals)
            eligible=any(x is not None for x in hvals+evals)
            total=h+e if eligible else None
            tier='No data' if not eligible else 'High priority' if h+e>=12 and h>=4 and e>=4 else 'Moderate priority' if h+e>=6 and h>=2 and e>=2 else 'Low priority'
            state='Complete' if all(x is not None for x in hvals+evals) else 'Partial' if eligible else 'No data'
            assert number(row['Hazard_score'])==h and number(row['Exposure_score'])==e and number(row['Priority_score'])==total,key
            assert row['Priority_tier']==tier and row['Priority_data_status']==state,key
            assert (str(row['Ranking_eligible']).lower() in ['true','1'])==eligible,key
            assert row['priority_scoring_policy']=='priority-zero-contribution-v1'
            assert len(json.loads(row['Priority_missing_reasons']))==sum(x is None for x in hvals+evals)
            if eligible:scores[key]=total
            for reference,label in [(old,'restricted_baseline'),(history,'historical_manuscript')]:
                for col in HAZARD+EXPOSURE+['Hazard_score','Exposure_score','Priority_score','Priority_tier','Priority_data_status']:
                    a,b=reference.at[key,col],row[col]
                    equal=(number(a)==number(b)) if col.endswith('_score') else a==b
                    if not equal:rows.append({'inchikey':key,'reference':label,'field':col,'before':a,'after':b})
        counts=Counter(scores.values());rank={};seen=0
        for value in sorted(counts,reverse=True):rank[value]=seen+1;seen+=counts[value]
        cutoff=sorted(scores.values(),reverse=True)[min(100,len(scores))-1]
        selected=[]
        for key,value in scores.items():
            row=current.loc[key]
            assert number(row['Priority_rank'])==rank[value] and number(row['Priority_tie_size'])==counts[value]
            assert (str(row['Top_n_selected']).lower() in ['true','1'])==(value>=cutoff)
            if value>=cutoff:selected.append(key)
        report={'passed':True,'candidate_sha256':digest(args.candidate),'baseline_sha256':digest(args.baseline),'n':len(current),'tiers':current.Priority_tier.value_counts().to_dict(),'status':current.Priority_data_status.value_counts().to_dict(),'ranked':len(scores),'top100_inclusive':len(selected),'cutoff_score':float(cutoff),'boundary_tie_size':counts[cutoff],'unchanged_evidence_fields':unchanged,'unchanged_provenance':provenance,'comparisons':{}}
        changes=pd.DataFrame(rows)
        for label,frame in changes.groupby('reference'):
            report['comparisons'][label]={'changed_compounds':frame.inchikey.nunique(),'changes_by_field':frame.groupby('field').inchikey.nunique().to_dict()}
        args.output.mkdir(parents=True,exist_ok=True)
        changes.to_csv(args.output/'per_compound_changes.csv',index=False)
        current.loc[selected,HAZARD+EXPOSURE+['Hazard_score','Exposure_score','Priority_score','Priority_rank','Priority_tie_size','Priority_data_status']].sort_values(['Priority_score'],ascending=False).to_csv(args.output/'top100_with_boundary_ties.csv')
        # Review ledgers preserve every affected record and the existing admission decision.
        current[current.gic_name_review_required.astype(str).eq('True')][['name_resolved','gic_match_method','GIC_inventory_listing_count','Exposure_inventory_score','exposure_inventory_unavailable_reason']].to_csv(args.output/'gic_name_review_ledger.csv')
        current[current.qsar_identity_status.eq('review_required')][['name_resolved','qsar_identity_reason']+HAZARD+['Priority_score','Priority_rank']].to_csv(args.output/'prediction_identity_review_ledger.csv')
        market=changes[(changes.reference=='historical_manuscript') & (changes.field=='Exposure_production_score')]
        current.loc[market.inchikey,['name_resolved','Exposure_production_score','exposure_production_unavailable_reason','Exposure_evidence']].to_csv(args.output/'production_market_review_ledger.csv')
        (args.output/'migration_audit.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ['unchanged_evidence_fields','unchanged_provenance']},indent=2))
if __name__=='__main__': main()
