"""One official output and one review output per migrated figure.

Legacy builders stay frozen. Running a migrated builder only replaces review;
promotion is a separate explicit action after the user accepts that review.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / 'Figure'
MANAGED = {'Fig1','Fig2','Fig3','ExtendedDataFig1','ExtendedDataFig2'}

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def source_profile():
    profile = json.loads((FIGURES/'managed_sources.json').read_text())
    profile['policy']['sha256'] = sha(ROOT/profile['policy']['path'])
    return profile

def verify_sources():
    profile = source_profile()
    for item in profile['files'].values():
        if sha(ROOT/item['path']) != item['sha256']:
            raise ValueError('Source hash changed: '+item['path'])
    with sqlite3.connect((ROOT/profile['files']['analysis']['path']).as_uri()+'?mode=ro',uri=True) as db:
        metadata = {k:json.loads(v) for k,v in db.execute('SELECT * FROM scenario_metadata')}
        assert metadata['run_id']==profile['run_id']
        assert metadata['csv_sha256']==profile['files']['publication']['sha256']
        assert db.execute('SELECT COUNT(*) FROM current_compounds').fetchone()[0]==profile['total']
    return profile

def code_hashes(folder):
    paths = [p for p in folder.rglob('*') if p.is_file() and p.suffix in {'.R','.py','.yml'}
             and not any(part in {'output','review','reference','audit','inputs','__pycache__'} or part.startswith('.') for part in p.relative_to(folder).parts)]
    paths += [FIGURES/'_shared'/n for n in ('managed.py','managed.R','five_level_policy.json','palette.R','theme.R','export.R','validation.R')]
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}

def paths_for(figure,state):
    return FIGURES/figure/state, ROOT/'output/figure_data'/figure/state

def replace_pair(image_stage,data_stage,image_target,data_target):
    """Rollback both targets on an ordinary failure; discard temporary backups on success."""
    pairs = [(image_stage,image_target),(data_stage,data_target)]
    backups = []
    installed = []
    try:
        for stage,target in pairs:
            target.parent.mkdir(parents=True,exist_ok=True)
            backup = None
            if target.exists():
                backup = Path(tempfile.mkdtemp(prefix='.previous-',dir=target.parent))
                backup.rmdir()
                target.rename(backup)
            backups.append((target,backup))
            stage.rename(target)
            installed.append(target)
    except Exception:
        for target in installed:
            shutil.rmtree(target)
        for target,backup in reversed(backups):
            if backup and backup.exists(): backup.rename(target)
        raise
    else:
        for _,backup in backups:
            if backup: shutil.rmtree(backup)

def update_catalog(figure,**changes):
    path = FIGURES/'catalog.json'
    catalog = json.loads(path.read_text())
    catalog['figures'][figure].update(changes)
    write_json(path,catalog)
    refresh_index()

def refresh_index():
    catalog = json.loads((FIGURES/'catalog.json').read_text())
    lines = ['# 图表清单','', '取图以本表为准。正式图位于 `output/`，待审图位于 `review/`。同一张图不保留编号预览。','',
             '| 图 | 正式版状态 | 正式文件 | 待审文件 | 说明 |','|---|---|---|---|---|']
    for fig,item in catalog['figures'].items():
        formal = '五级版，已确认' if item['formal']=='current' else '历史版，尚未更新'
        approved = f'[PNG]({fig}/output/{fig}.png) · [PDF]({fig}/output/{fig}.pdf)' if item['formal']=='current' else '暂勿用于新稿'
        review = f'[PNG]({fig}/review/{fig}.png) · [PDF]({fig}/review/{fig}.pdf)' if item.get('review') else '—'
        lines.append(f'| {fig} | {formal} | {approved} | {review} | {item["note"]} |')
    lines += ['', '新版图读取 2026-10-27 的整数评分；五级分类仅在绘图层派生。正式 CSV、SQLite 和 Dashboard 未随之改为五级。',
              '', '101 个 Level 1 化合物的外部分类型交接文件是待回传的研究输入，不属于待清理的图形预览。','']
    (FIGURES/'INDEX.md').write_text('\n'.join(lines))

def run(folder):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # No arbitrary/versioned destination directories.
    if folder.name not in MANAGED: raise ValueError('Figure not migrated')
    profile = verify_sources()
    staging = Path(tempfile.mkdtemp(prefix='.building-',dir=folder))
    data_stage = None
    try:
        if folder.name=='ExtendedDataFig1':
            subprocess.run([sys.executable,str(folder/'prepare_data.py'),str(staging)],cwd=ROOT,check=True)
        subprocess.run(['Rscript',str(folder/'build.R'),str(staging)],cwd=ROOT,check=True)
        for suffix in ('png','pdf'):
            assert (staging/f'{folder.name}.{suffix}').is_file()
        facts = json.loads((staging/'caption_facts.json').read_text())
        (staging/'caption_facts.json').unlink()
        qa = {}
        if folder.name=='ExtendedDataFig1':
            spec=importlib.util.spec_from_file_location('alignment',folder/'audit_alignment.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            qa['alignment'] = module.check(staging,staging/'source_data')
            (staging/f'{folder.name}.svg').unlink()
        images,data_target = paths_for(folder.name,'review')
        data_stage = staging/'source_data'
        assert data_stage.is_dir()
        manifest = {'schema_version':2,'figure':folder.name,'status':'review','source':profile,
                    'source_data_dir':str(data_target.relative_to(ROOT)),'code':code_hashes(folder),
                    'source_data':{str(p.relative_to(data_stage)):sha(p) for p in sorted(data_stage.rglob('*')) if p.is_file()},
                    'outputs':{p.name:sha(p) for p in staging.iterdir() if p.is_file()},'facts':facts,'qa':qa}
        write_json(staging/'manifest.json',manifest)
        # Move table staging outside image staging before swapping the two directories.
        table_parent = ROOT/profile['data_root']/folder.name
        table_parent.mkdir(parents=True,exist_ok=True)
        detached = Path(tempfile.mkdtemp(prefix='.building-',dir=table_parent));detached.rmdir()
        data_stage.rename(detached);data_stage=detached
        replace_pair(staging,data_stage,images,data_target)
        update_catalog(folder.name,review=True,note='新版已生成，等待审阅')
        print(f'{folder.name}: {images/folder.name}.png (review only)')
    finally:
        if staging.exists(): shutil.rmtree(staging)
        if data_stage and data_stage.exists() and data_stage.name.startswith('.building-'): shutil.rmtree(data_stage)

def approve(figure):
    if figure not in MANAGED: raise ValueError('Figure is deferred, not eligible for promotion')
    review,data_review=paths_for(figure,'review')
    output,data_output=paths_for(figure,'output')
    manifest=json.loads((review/'manifest.json').read_text())
    assert manifest['source']==verify_sources()
    assert manifest['code']==code_hashes(FIGURES/figure), 'Code changed after review; rebuild first'
    for name,digest in manifest['outputs'].items(): assert sha(review/name)==digest
    for name,digest in manifest['source_data'].items(): assert sha(data_review/name)==digest
    image_stage=Path(tempfile.mkdtemp(prefix='.promoting-',dir=output.parent))
    data_stage=Path(tempfile.mkdtemp(prefix='.promoting-',dir=data_output.parent))
    try:
        shutil.copytree(review,image_stage,dirs_exist_ok=True)
        shutil.copytree(data_review,data_stage,dirs_exist_ok=True)
        manifest['status']='approved'
        manifest['source_data_dir']=str(data_output.relative_to(ROOT))
        write_json(image_stage/'manifest.json',manifest)
        replace_pair(image_stage,data_stage,output,data_output)
        shutil.rmtree(review);shutil.rmtree(data_review)
        update_catalog(figure,formal='current',review=False,note='已确认，可用于新稿')
    finally:
        for path in (image_stage,data_stage):
            if path.exists(): shutil.rmtree(path)
