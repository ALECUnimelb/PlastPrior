"""Versioned rescore of a frozen export, retaining all original evidence tables.

Run: python -m plastprior.scenario_export --source output/2026-10-26 --output output/2026-10-27
The source and its embedded stage archives are never rewritten. In the new full
archive, current_compounds is the authoritative current view; compounds and
embedded stage artifacts retain their baseline meaning for audit reconstruction.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from .scoring_scenarios import default_policy, score_population, score_record


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def cell(value):
    return '' if value is None else str(value)


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def export_scenario(source, output, policy=None):
    source, output = Path(source).resolve(), Path(output).absolute()
    policy = default_policy() if policy is None else policy
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Output must be a new directory outside the source export.')
    names = ['PlastPrior_results.csv', 'PlastPrior_results.sqlite', 'PlastPrior_dashboard.sqlite']
    hashes = {name: sha(source / name) for name in names}
    with (source / names[0]).open(newline='') as f:
        reader = csv.DictReader(f)
        original_fields = reader.fieldnames
        baseline = list(reader)
    with sqlite3.connect((source / names[2]).as_uri() + '?mode=ro', uri=True) as db:
        meta = dict(db.execute('select key,value from metadata'))
        if meta['csv_sha256'] != hashes[names[0]]:
            raise ValueError('Source CSV and Dashboard database are not paired.')
    scored = score_population(baseline, policy)
    derived_fields = [*score_record(baseline[0], policy), 'Priority_rank', 'Priority_tie_size', 'Top_n_selected']
    fields = list(dict.fromkeys([*original_fields, *derived_fields]))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-rounded'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.scenario-', dir=output.parent) as temp:
        staging = Path(temp) / 'export'; staging.mkdir()
        csv_path = staging / names[0]
        with csv_path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows({k: cell(row.get(k)) for k in fields} for row in scored)
        current_hash = sha(csv_path)
        provenance = {'run_id': run_id, 'source': str(source), 'source_sha256': hashes,
                      'base_run_id': meta['run_id'], 'policy': policy,
                      'policy_sha256': hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',', ':')).encode()).hexdigest(),
                      'implementation_sha256': {n: sha(Path(__file__).with_name(n)) for n in ['scoring_scenarios.py', 'scenario_export.py']},
                      'csv_sha256': current_hash,
                      'scope': 'Current scores in scenario_results/current_compounds; original compounds and stage artifacts remain immutable baseline audit.'}
        for name in names[1:]:
            shutil.copy2(source / name, staging / name)
        # Preserve the original archive tables, including delta snapshots that depend on them.
        with sqlite3.connect(staging / names[1]) as db:
            if db.execute("select 1 from sqlite_master where name='scenario_results'").fetchone():
                raise ValueError('Use the immutable original export as the scenario source.')
            db.execute('CREATE TABLE scenario_results (' + ','.join(quote(f)+' TEXT'+(' PRIMARY KEY' if f=='inchikey' else '') for f in fields)+')')
            db.executemany('INSERT INTO scenario_results VALUES ('+','.join('?' for _ in fields)+')',
                           [[cell(row.get(f)) for f in fields] for row in scored])
            original = [r[1] for r in db.execute('pragma table_info(compounds)')]
            select = ['s.'+quote(f) if f in derived_fields else 'c.'+quote(f) for f in original]
            select += ['s.'+quote(f) for f in derived_fields if f not in original]
            db.execute('CREATE VIEW current_compounds AS SELECT '+','.join(select)+' FROM compounds c JOIN scenario_results s USING(inchikey)')
            db.execute('CREATE TABLE scenario_metadata (key TEXT PRIMARY KEY,value_json TEXT NOT NULL)')
            db.executemany('INSERT INTO scenario_metadata VALUES (?,?)', [(k,json.dumps(v)) for k,v in provenance.items()])
        with sqlite3.connect(staging / names[2]) as db:
            old = [r[1] for r in db.execute('pragma table_info(compound_audit)')]
            db.execute('CREATE TABLE baseline_scoring AS SELECT inchikey_std,'+','.join(quote(f) for f in derived_fields if f in old)+' FROM compound_audit')
            for field in derived_fields:
                if field not in old:
                    db.execute('ALTER TABLE compound_audit ADD COLUMN '+quote(field)+' TEXT')
            statement = 'UPDATE compound_audit SET '+','.join(quote(f)+'=?' for f in derived_fields)+' WHERE inchikey_std=?'
            db.executemany(statement, [[cell(row[f]) for f in derived_fields]+[row['inchikey']] for row in scored])
            new_meta = {'run_id':run_id, 'csv_sha256':current_hash, 'priority_policy':policy['policy_version'],
                        'base_run_id':meta['run_id'], 'scenario_provenance':json.dumps(provenance),
                        'readme':'H/E weighted sums rounded half up separately. Priority=sum of rounded H/E. Labels: L<4, M<8, H<12, otherwise vH. Original evidence preserved; weighted sums retained as *_score_raw.'}
            db.executemany('INSERT OR REPLACE INTO metadata VALUES (?,?)', new_meta.items())
            for field in derived_fields:
                spec = {'field':field,'source_field':field,'definition':'Derived by '+policy['policy_version']+'; see scoring_config_json and scenario_provenance.'}
                db.execute('INSERT OR REPLACE INTO data_dictionary VALUES (?,?)',(field,json.dumps(spec)))
        # Verify every CSV field against the current archive and every changed detail field.
        for name, table, key in [(names[1],'scenario_results','inchikey'),(names[2],'compound_audit','inchikey_std')]:
            with sqlite3.connect(staging / name) as db:
                if db.execute('pragma integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('SQLite integrity failed: '+name)
                check_fields = fields if table == 'scenario_results' else derived_fields
                for row in scored:
                    actual = db.execute('SELECT '+','.join(map(quote,check_fields))+' FROM '+table+' WHERE '+key+'=?',(row['inchikey'],)).fetchone()
                    if actual != tuple(cell(row.get(f)) for f in check_fields):
                        raise ValueError('Export mismatch: '+row['inchikey'])
        (staging/'scoring_config.json').write_text(json.dumps(policy,indent=2)+'\n')
        summary = {**provenance, 'rows':len(scored), 'levels':dict(Counter(r['Priority_tier'] for r in scored)),
                   'top_n_selected':sum(r['Top_n_selected'] is True for r in scored),
                   'verification':'all CSV fields and derived Dashboard fields match; both SQLite integrity checks passed',
                   'output_sha256':{name:sha(staging/name) for name in names}}
        # A portable chart source contains exactly the same integer domains and ranks.
        with (staging/'score_chart_data.csv').open('w',newline='') as f:
            columns=['inchikey','Hazard_score','Exposure_score','Priority_score','Hazard_label','Exposure_label','Priority_level','Priority_rank','Top_n_selected']
            writer=csv.DictWriter(f,fieldnames=columns,lineterminator='\n');writer.writeheader()
            writer.writerows({k:cell(r[k]) for k in columns} for r in scored)
        (staging/'scenario_manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
        if {name:sha(source/name) for name in names} != hashes:
            raise ValueError('Source changed during scoring.')
        staging.rename(output)
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,help='Scoring configuration JSON, or a Dashboard scenario configuration export.')
    args=parser.parse_args()
    policy=None
    if args.config:
        config=json.loads(args.config.read_text())
        if config.get('format') == 'plastprior-scenario-v1':
            if config.get('base_csv_sha256') != sha(args.source/'PlastPrior_results.csv'):
                parser.error('Scenario configuration belongs to a different source CSV.')
            policy=config['config']
        else:
            policy=config
    print(json.dumps(export_scenario(args.source,args.output,policy),indent=2))
