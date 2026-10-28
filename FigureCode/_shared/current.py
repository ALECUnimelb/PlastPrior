"""Build one figure from the explicitly locked PlastPrior analysis export."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from result_paths import figure_paths
from managed import replace_pair

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / 'FigureCode'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def verify_sources():
    source = json.loads((FIGURES / 'figure_sources.json').read_text())
    for record in source['files'].values():
        if sha(ROOT / record['path']) != record['sha256']:
            raise ValueError('Locked PlastPrior source changed: ' + record['path'])
    for name, fingerprint in source['policies'].items():
        if sha(ROOT / 'plastprior' / name) != fingerprint:
            raise ValueError('Analysis policy differs from figure lock: ' + name)
    with sqlite3.connect((ROOT / source['files']['analysis']['path']).as_uri() + '?mode=ro', uri=True) as db:
        metadata = {k: json.loads(v) for k, v in db.execute('SELECT * FROM run_metadata')}
        assert metadata['run_id'] == source['run_id']
        assert metadata['csv_sha256'] == source['files']['publication']['sha256']
        assert dict(db.execute('SELECT Priority_tier,COUNT(*) FROM compounds GROUP BY Priority_tier')) == source['population']
        assert db.execute("SELECT COUNT(*) FROM compounds WHERE priority_result_role != 'analysis_after_eligibility_audit' OR ranking_result_role != 'analysis_rank_with_zero_contribution_policy'").fetchone()[0] == 0
    return source

def run(folder):
    parser = argparse.ArgumentParser(description=__doc__)
    # Destinations are fixed; alternate/versioned paths are intentionally unsupported.
    if folder.name == 'ExtendedDataFig4':
        parser.add_argument('--dashboard-url', default='http://127.0.0.1:5198/')
    args = parser.parse_args()
    from preparation import verify_prepared
    prepared_record = verify_prepared(folder.name) if folder.name != 'ExtendedDataFig4' else None
    source = prepared_record['source'] if prepared_record else verify_sources()
    output, data_output = figure_paths(folder.name)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.building-', dir=output.parent))
    try:
        if folder.name == 'ExtendedDataFig1':
            subprocess.run([sys.executable, str(folder / 'prepare_data.py'), str(staging)], cwd=ROOT, check=True)
        if folder.name == 'ExtendedDataFig4':
            subprocess.run(['node', str(folder / 'capture.mjs'), args.dashboard_url, str(staging)], cwd=ROOT, check=True)
        else:
            shutil.copytree(data_output,staging/'source_data')
            (staging/'caption_facts.json').write_text(json.dumps(prepared_record['facts']))
            subprocess.run(['Rscript', str(folder / 'build.R'), str(staging)], cwd=ROOT, check=True)
        png = staging / (folder.name + '.png')
        if not png.is_file():
            raise ValueError('Figure not generated: ' + str(png))
        data_output = figure_paths(folder.name)[1]
        manifest = {'figure': folder.name, 'source': source,
                    'source_data_dir': str(data_output.relative_to(ROOT)),
                    'code': {str(p.relative_to(ROOT)): sha(p) for base in ([folder, FIGURES / '_shared'] + ([FIGURES / '_shared/sensitivity'] if folder.name == 'ExtendedDataFig3' else []))
                             for p in base.rglob('*') if p.is_file() and p.suffix in {'.R', '.py', '.yml', '.mjs'}
                             and not any(x in p.parts for x in ['output','reference','audit','inputs'])
                             and not any(x.startswith('.building-') for x in p.parts)},
                    'source_data': {str(p.relative_to(staging / 'source_data')): sha(p) for p in (staging / 'source_data').rglob('*') if p.is_file()},
                    'outputs': {str(p.relative_to(staging)): sha(p) for p in staging.rglob('*') if p.is_file() and 'source_data' not in p.relative_to(staging).parts}}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if prepared_record:
            prepared_record['source_data']=manifest['source_data']
            prepared_record['images_require_update']=False
            (staging/'preparation.json').write_text(json.dumps(prepared_record,indent=2)+'\n')
        staged_data = staging/'source_data'
        staged_data.mkdir(exist_ok=True)
        detached=Path(tempfile.mkdtemp(prefix='.tables-',dir=ROOT))
        detached.rmdir();staged_data.rename(detached)
        try: replace_pair(staging,detached,output,data_output)
        finally: shutil.rmtree(detached,ignore_errors=True)
        shutil.rmtree(staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f'{folder.name}: {output / png.name}')
