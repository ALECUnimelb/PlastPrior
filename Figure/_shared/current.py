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

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / 'Figure'

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
        assert db.execute("SELECT COUNT(*) FROM compounds WHERE priority_result_role != 'analysis_after_eligibility_audit' OR ranking_result_role != 'analysis_rank_within_complete_evidence_pool'").fetchone()[0] == 0
    return source

def run(folder):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=folder / 'output')
    if folder.name == 'ExtendedDataFig4':
        parser.add_argument('--dashboard-url', default='http://127.0.0.1:5198/')
    args = parser.parse_args()
    source = verify_sources()
    output = args.output_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.building-', dir=output.parent))
    try:
        if folder.name == 'ExtendedDataFig1':
            subprocess.run([sys.executable, str(folder / 'prepare_data.py'), str(staging)], cwd=ROOT, check=True)
        if folder.name == 'ExtendedDataFig4':
            subprocess.run(['node', str(folder / 'capture.mjs'), args.dashboard_url, str(staging)], cwd=ROOT, check=True)
        else:
            subprocess.run(['Rscript', str(folder / 'build.R'), str(staging)], cwd=ROOT, check=True)
        png = staging / (folder.name + '.png')
        if not png.is_file():
            raise ValueError('Figure not generated: ' + str(png))
        manifest = {'figure': folder.name, 'source': source,
                    'code': {str(p.relative_to(ROOT)): sha(p) for base in ([folder, FIGURES / '_shared'] + ([FIGURES / 'Fig4'] if folder.name == 'ExtendedDataFig3' else []))
                             for p in base.rglob('*') if p.is_file() and p.suffix in {'.R', '.py', '.yml', '.mjs'}
                             and not any(x in p.parts for x in ['output','reference','audit','inputs'])
                             and not any(x.startswith('.building-') for x in p.parts)},
                    'outputs': {str(p.relative_to(staging)): sha(p) for p in staging.rglob('*') if p.is_file()}}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if output.exists():
            history = FIGURES / '.history' / folder.name
            history.parent.mkdir(exist_ok=True)
            if not history.exists():
                output.rename(history)
            else:
                # Subsequent output is reproducible; the original is retained once.
                shutil.rmtree(output)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f'{folder.name}: {output / png.name}')
