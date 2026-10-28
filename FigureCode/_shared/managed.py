"""One current image/data set per figure; approval is catalog metadata only."""
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from result_paths import figure_paths, relocated, verify_code, RESULT, manifest_path, artifact_path

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / 'FigureCode'
MANAGED = {'Fig1','Fig2','Fig3','ExtendedDataFig1','ExtendedDataFig2','Fig4'}

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
    paths += [FIGURES/'_shared'/n for n in ('result_paths.py','managed.py','managed.R','plot_data.R','preparation.py','five_level_policy.json','palette.R','theme.R','export.R','validation.R')]
    if folder.name in {'Fig5','ExtendedDataFig3'}:
        paths += [FIGURES/'_shared'/n for n in ('current.R','priority_policy.R','scenarios.R')]
    if folder.name=='ExtendedDataFig3':
        paths += [p for p in (FIGURES/'_shared/sensitivity').rglob('*') if p.suffix in {'.R','.yml'}]
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}

def paths_for(figure,state):
    return figure_paths(figure, state)

def replace_pair(image_stage,data_stage,image_target,data_target):
    """Publish one figure's validated files without deleting neighbouring figures."""
    sys.path.insert(0,str(ROOT))
    from plastprior.result_storage import update_lock, replace_directory
    if image_target != RESULT/'figures' or data_target.parent != RESULT/'figure_data':
        raise ValueError('Figure destinations must be the fixed current result paths')
    if not image_stage.is_dir() or not data_stage.is_dir():
        raise FileNotFoundError('Both figure and table staging directories are required')
    name = data_target.name
    with update_lock(RESULT):
        stage = Path(tempfile.mkdtemp(prefix='.figure-install-',dir=ROOT))
        try:
            shutil.copytree(RESULT,stage,dirs_exist_ok=True,copy_function=os.link)
            # Hard links are only for untouched files. Never write through one.
            old = manifest_path(name)
            if old.exists():
                record=json.loads(old.read_text())
                for filename in record.get('outputs',record.get('output_hashes',{})):
                    target=stage/artifact_path(name,filename).relative_to(RESULT)
                    target.unlink(missing_ok=True)
            new_data=stage/'figure_data'/name
            if new_data.exists(): shutil.rmtree(new_data)
            shutil.copytree(data_stage,new_data)
            metadata=stage/'figure_data/_metadata'/name
            if metadata.exists(): shutil.rmtree(metadata)
            metadata.mkdir(parents=True)
            (stage/'figures').mkdir(exist_ok=True)
            for source in image_stage.iterdir():
                if not source.is_file(): continue
                target=(stage/'figures' if source.suffix in {'.png','.pdf','.xlsx'} else metadata)/source.name
                target.unlink(missing_ok=True)
                shutil.copy2(source,target)
            replace_directory(stage,RESULT)
        finally:
            if stage.exists(): shutil.rmtree(stage)


def update_catalog(figure,**changes):
    path = FIGURES/'catalog.json'
    catalog = json.loads(path.read_text())
    catalog['figures'][figure].update(changes)
    write_json(path,catalog)
    refresh_index()

def refresh_index():
    catalog = json.loads((FIGURES/'catalog.json').read_text())
    lines = ['# 图表清单','', '每个图号只有一套当前文件。状态由本表记录，生成新版替换同名文件，不保留并行正式/待审目录。','',
             '| 图 | 当前状态 | 文件 | 说明 |','|---|---|---|---|']
    for fig,item in catalog['figures'].items():
        status = '待审' if item['review'] else ('已确认' if item['formal']=='current' else '旧版，待更新')
        links = f'[PNG](../result/figures/{fig}.png)'
        if (RESULT/'figures'/f'{fig}.pdf').exists(): links += f' · [PDF](../result/figures/{fig}.pdf)'
        lines.append(f'| {fig} | {status} | {links} | {item["note"]} |')
    lines += ['', '五级分类仅在绘图层派生，当前 CSV 和 SQLite 的评分排名未改变。', '',
              '明确保留：Level1_identity（名单）、Level1_classification_tree（分类树）、Sensitivity_analysis（旧敏感性分析）。',
              '所有图片位于 `result/figures/`，数据位于 `result/figure_data/`，唯一审阅 PPT 位于 `result/`，保留用户命名。','']
    (FIGURES/'INDEX.md').write_text('\n'.join(lines))


def run(folder):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # No arbitrary/versioned destination directories.
    if folder.name not in MANAGED: raise ValueError('Figure not migrated')
    from preparation import verify_prepared
    prepared_record = verify_prepared(folder.name)
    profile = prepared_record['source']
    staging = Path(tempfile.mkdtemp(prefix='.building-',dir=folder))
    data_stage = None
    try:
        shutil.copytree(RESULT/'figure_data'/folder.name,staging/'source_data')
        write_json(staging/'caption_facts.json',prepared_record['facts'])
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
        prepared_record['images_require_update']=False
        prepared_record['source_data']=manifest['source_data']
        write_json(staging/'preparation.json',prepared_record)
        replace_pair(staging,data_stage,images,data_target)
        update_catalog(folder.name,review=True,note='新版已生成，等待审阅', **({'publication_mode':'rendered'} if folder.name=='Fig4' else {}))
        print(f'{folder.name}: {images/folder.name}.png (review only)')
    finally:
        if staging.exists(): shutil.rmtree(staging)
        if data_stage and data_stage.exists() and data_stage.name.startswith('.building-'): shutil.rmtree(data_stage)

def approve(figure):
    if figure not in MANAGED: raise ValueError('Figure is deferred, not eligible for promotion')
    manifest=relocated(json.loads(manifest_path(figure).read_text()))
    assert manifest['status']=='review'
    assert manifest['source']==verify_sources()
    verify_code(manifest['code'],code_hashes(FIGURES/figure))
    for name,digest in manifest['outputs'].items(): assert sha(artifact_path(figure,name))==digest
    for name,digest in manifest['source_data'].items(): assert sha(paths_for(figure,'review')[1]/name)==digest
    manifest['status']='approved'
    write_json(manifest_path(figure),manifest)
    update_catalog(figure,formal='current',review=False,note='已确认，可用于新稿')
