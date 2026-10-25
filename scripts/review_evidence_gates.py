"""Audit every retained evidence-gate decision without changing admission."""
import argparse,json
from collections import Counter
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stages',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=a.stages/'stage6';a.output.mkdir(parents=True,exist_ok=True)
def read(path):return pd.read_csv(path,dtype=str,keep_default_na=False)
g=read(r/'6a/gic_compound_audit.csv');m=read(r/'6a/market_source_records.csv');c=read(r/'6b/exposure_candidate_decisions.csv')
assert g.inchikey.is_unique and len(g)==15125
name=g[g.eligibility_status.eq('name_association_review_required')].copy()
assert len(name)==1132 and name.eligible_inventory_count.isin(['','0']).all()
name['review_disposition']='Retain exclusion: name-only association has no accepted full-key/CID bridge in the recorded lookup. Independent identity confirmation is required before restoration.'
name.to_csv(a.output/'gic_all_name_associations_review.csv',index=False)
negative=m[['quantity_lower_tonnes','quantity_upper_tonnes']].apply(pd.to_numeric,errors='coerce').lt(0).any(axis=1)
assert m.loc[negative,'numeric_eligible'].eq('False').all()
assert m.loc[m.identity_match_status.eq('ambiguous_dashboard_cas_mapping'),'qualitative_eligible'].eq('False').all()
assert c.loc[c.audit_id.isin(m.loc[negative,'audit_id']),'analysis_eligible'].eq('False').all()
market=read(r/'6a/market_gate_audit.csv');changed=market[market.presence_changed_by_gate.eq('True')]
review=m[m.inchikey.isin(changed.inchikey)].copy()
review['review_disposition']=review.apply(lambda x:'Retain admitted evidence' if x.qualitative_eligible=='True' else 'Retain exclusion: '+x.qualitative_exclusion_reasons,axis=1)
review.to_csv(a.output/'market_presence_affected_source_review.csv',index=False)
m.loc[negative].to_csv(a.output/'negative_quantity_exclusions.csv',index=False)
report={'policy_change':False,'restored_contributions':0,'reason':'No new independently verified identity/source evidence was supplied by this computational review. Preserve current gates; unresolved identities remain reviewable, not confirmed false.',
'gic_compounds':len(g),'gic_statuses':g.eligibility_status.value_counts().to_dict(),'gic_name_reviews':len(name),'market_source_rows_reviewed':len(m),'market_presence_changed_compounds':len(changed),'negative_quantity_rows':int(negative.sum()),'negative_quantity_compounds':m.loc[negative,'inchikey'].nunique(),'qualitative_exclusions':dict(Counter(reason for text in m.qualitative_exclusion_reasons for reason in json.loads(text))),'numeric_exclusions':dict(Counter(reason for text in m.numeric_exclusion_reasons for reason in json.loads(text)))}
(a.output/'evidence_gate_review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
