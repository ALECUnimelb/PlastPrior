"""Prepare figure inputs separately; install a complete validated set together."""
from pathlib import Path
import csv
from decimal import Decimal, InvalidOperation
import json
import os
import shutil
import subprocess
import sys
import tempfile
from result_paths import ROOT, RESULT, manifest_path, relocated
from managed import sha, write_json, code_hashes

CURRENT = ('Fig1','Fig2','Fig3','Fig4','ExtendedDataFig1','ExtendedDataFig2','SILevel1Evidence')
FROZEN = ('Fig5','ExtendedDataFig3')

def hashes(folder):
    return {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and p.name != '.DS_Store'}

def equivalent(a, b):
    """CSV numeric formatting changes are not changes to observations."""
    if sha(a) == sha(b): return True
    if a.suffix == '.json': return relocated(json.loads(a.read_text())) == relocated(json.loads(b.read_text()))
    if a.suffix != '.csv': return False
    def cell(x):
        try: return Decimal(x)
        except InvalidOperation: return x
    def rows(p):
        with p.open(newline='',encoding='utf-8-sig') as f:
            return [[cell(c) for c in row] for row in csv.reader(f)]
    return rows(a) == rows(b)

def preparation_path(name):
    return manifest_path(name).with_name('preparation.json')

def verify_prepared(name):
    path = preparation_path(name)
    if not path.exists(): raise ValueError('Prepare figure data first: FigureCode/prepare_data.py --figures '+name)
    record = json.loads(path.read_text())
    folder = RESULT/'figure_data'/name
    if hashes(folder) != record['source_data']: raise ValueError('Prepared figure inputs changed: '+name)
    lock_name = 'managed_sources.json' if name in CURRENT else 'figure_sources.json'
    lock = json.loads((ROOT/'FigureCode'/lock_name).read_text())
    if lock['files'] != record['source']['files']:
        raise ValueError('Source lock changed; prepare figure data again: '+name)
    return record

def prepare(names, *, check_existing=False, install=True):
    if not names or not set(names) <= set(CURRENT+FROZEN): raise ValueError('Unknown figure selection')
    from managed import verify_sources
    from current import verify_sources as verify_frozen
    profiles = {}
    if set(names) & set(CURRENT): profiles['current'] = verify_sources()
    if set(names) & set(FROZEN): profiles['frozen'] = verify_frozen()
    sys.path.insert(0,str(ROOT))
    from plastprior.result_storage import update_lock, replace_directory
    records = {}
    # Holding the update lock prevents another publisher from replacing our inputs.
    with update_lock(RESULT), tempfile.TemporaryDirectory(prefix='.figure-prepare-',dir=ROOT) as temp:
        temp = Path(temp)
        original_files = {n: hashes(RESULT/'figure_data'/n) for n in names}
        for name in names:
            folder = ROOT/'FigureCode'/('Supplementary/'+name if name=='SILevel1Evidence' else name)
            stage = temp/name; stage.mkdir()
            env = dict(os.environ, PLASTPRIOR_FIGURE_PHASE='prepare')
            if name == 'ExtendedDataFig1':
                subprocess.run([sys.executable,str(folder/'prepare_data.py'),str(stage)],cwd=ROOT,env=env,check=True)
            if name == 'SILevel1Evidence':
                import importlib.util
                spec=importlib.util.spec_from_file_location('si_data',folder/'prepare.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                payload=module.make_payload()
                previous=RESULT/'figure_data'/name/'si_payload.json'
                if previous.exists():
                    old=json.loads(previous.read_text())
                    before={r['inchikey'] for r in old['rows']}; after={r['inchikey'] for r in payload['rows']}
                    payload['changes']['membership_change']=old['changes'].get('membership_change',{}) if before==after else {'added':sorted(after-before),'removed':sorted(before-after)}
                module.write_payload(payload,stage/'source_data')
                write_json(stage/'caption_facts.json',{'cohort':len(payload['rows'])})
            else:
                subprocess.run(['Rscript',str(folder/'prepare.R'),str(stage)],cwd=ROOT,env=env,check=True)
            tables=stage/'source_data'; current=RESULT/'figure_data'/name
            changed=[]
            for p in tables.rglob('*'):
                if not p.is_file(): continue
                rel=p.relative_to(tables); old=current/rel
                if old.exists() and p.name!='plot_data.rds':
                    if equivalent(p,old):
                        # Preserve the existing bytes and historical build hashes.
                        shutil.copy2(old,p)
                    else: changed.append(str(rel))
                elif not old.exists() and p.name!='plot_data.rds': changed.append(str(rel))
            if check_existing and changed: raise ValueError(f'{name}: numerical tables differ: {changed}')
            # Geometry QA from the last render is retained until the next render.
            for p in current.rglob('*'):
                if p.is_file() and p.name != '.DS_Store' and not (tables/p.relative_to(current)).exists():
                    target=tables/p.relative_to(current);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            facts=json.loads((stage/'caption_facts.json').read_text())
            record={'figure':name,'source':profiles['current' if name in CURRENT else 'frozen'],
                    'source_data':hashes(tables),'code':code_hashes(folder),'facts':facts,
                    'images_require_update':bool(changed) or (json.loads(preparation_path(name).read_text()).get('images_require_update',False) if preparation_path(name).exists() else False),'changed_tables':changed,
                    'source_role':'current' if name in CURRENT else 'fixed legacy baseline'}
            if name=='Fig4':
                import importlib.util
                spec=importlib.util.spec_from_file_location('composition_check',folder/'verify.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                module.verify_tables(tables,ROOT/profiles['current']['files']['publication']['path'])
            records[name]=record
            print(name+': prepared; '+('tables match current figures' if not changed else 'images require update'))
        for name in names:
            if hashes(RESULT/'figure_data'/name)!=original_files[name]:raise ValueError('Input tables changed during preparation: '+name)
        if install:
            stage=temp/'result'
            shutil.copytree(RESULT,stage,copy_function=os.link)
            for name,record in records.items():
                destination=stage/'figure_data'/name
                if destination.exists():shutil.rmtree(destination)
                shutil.copytree(temp/name/'source_data',destination)
                meta=stage/preparation_path(name).relative_to(RESULT)
                meta.unlink(missing_ok=True);write_json(meta,record)
            replace_directory(stage,RESULT)
    return records
