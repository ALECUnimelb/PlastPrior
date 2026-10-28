"""Decode current identity audits and aggregate provenance without historical tables."""
from pathlib import Path
import csv,json,sqlite3,sys
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from plastprior.export import read_artifact_records

def prepare(destination):
    lock=json.loads((ROOT/'FigureCode/managed_sources.json').read_text())
    db=sqlite3.connect((ROOT/lock['files']['analysis']['path']).as_uri()+'?mode=ro',uri=True)
    def sid(source,table):
        return {'fcchumon_s1':'FCChumon_S1','fcchumon_s2':'FCChumon_S2'}.get(table,source)
    record_sources={r:sid(s,t) for r,s,t in db.execute('select record_id,source_id,table_id from source_records')}
    counts=Counter(record_sources.values())
    memberships=sorted({(k,record_sources[r]) for k,r in db.execute('select inchikey,record_id from compound_memberships')})
    linked_records={r for (r,) in db.execute('select record_id from compound_memberships')}
    distinct=Counter(s for k,s in memberships)
    aggregate=Counter();resolved=Counter();seen=set()
    for row in read_artifact_records(db,'stage2/resolved_records.csv'):
        rid=row['record_id'];seen.add(rid);source=record_sources[rid]
        available=lambda field: str(row[field]).lower()=='true'
        identifier='reported_smiles' if available('smiles_reported_available') else 'inchikey_only' if available('inchikey_reported_available') else 'cas_only' if available('cas_reported_available') else 'no_identifier'
        ok=str(row['aggregation_eligible']).lower()=='true'
        assert ok==(rid in linked_records)
        route=row['resolution_route'] or 'unresolved'
        aggregate[(source,identifier,route,'resolved_records' if ok else 'unresolved_records')]+=1
        if ok:resolved[source]+=1
    assert seen==set(record_sources)
    out=Path(destination)/'source_data';out.mkdir(parents=True,exist_ok=True)
    def write(name,fields,rows):
        with (out/(name+'.csv')).open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(fields);w.writerows(rows)
    write('record_flow',['source_id','identifier_class','recovery_route','resolution_state','record_count'],[(*k,v) for k,v in sorted(aggregate.items())])
    write('memberships',['inchikey_std','source_id','member','definition_version'],[(k,s,1,'PlastPrior-resolved-record-membership-v1') for k,s in memberships])
    write('source_attrition',['source_id','harmonized_record_count','resolved_record_count','unresolved_record_count','unique_compound_count'],[(s,counts[s],resolved[s],counts[s]-resolved[s],distinct[s]) for s in sorted(counts)])
    label={'NORMAN_MPLEACH':'MPLEACH','FCChumon_S1':'FCChumon S1','FCChumon_S2':'FCChumon S2'}
    write('source_catalog',['source_id','display_label','formal_name','membership_column','membership_definition_version'],[(s,label.get(s,s),s,'source_member_'+s,'PlastPrior-resolved-record-membership-v1') for s in sorted(counts)])
    return {'records':len(seen),'record_links':len(linked_records),'compound_source_pairs':len(memberships),'source_tables':len(counts)}

if __name__=='__main__':print(prepare(sys.argv[1]))
