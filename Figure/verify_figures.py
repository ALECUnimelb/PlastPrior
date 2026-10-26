"""Verify current scientific derivations and unchanged figure provenance after relocation."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    subprocess.run([sys.executable, str(ROOT/'scripts/audit_figure_refresh.py')], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT/'Figure/ExtendedDataFig1/audit_alignment.py')], cwd=ROOT, check=True)
    lock = json.loads((ROOT/'Figure/figure_sources.json').read_text())
    ledger = ROOT/'audit_archive/workspace_migration_20261026/code_relocations.json'
    relocations = json.loads(ledger.read_text()) if ledger.exists() else {}
    figures = [f'Fig{i}' for i in range(1,6)] + [f'ExtendedDataFig{i}' for i in range(1,5)]
    relocated = []
    for fig in figures:
        folder = ROOT/'Figure'/fig/'output'
        manifest = json.loads((folder/'manifest.json').read_text())
        assert manifest['source'] == lock, ('source lock', fig)
        for name, expected in manifest['code'].items():
            observed = sha(ROOT/name)
            if observed != expected:
                record = relocations.get(name, {})
                assert record.get('before_sha256') == expected and record.get('after_sha256') == observed, ('stale code', fig, name)
                relocated.append({'figure': fig, 'path': name, 'reason': record['reason']})
        for name, expected in manifest['outputs'].items():
            assert sha(folder/name) == expected, ('changed output', fig, name)
        data = ROOT/manifest['source_data_dir']
        for name, expected in manifest['source_data'].items():
            assert sha(data/name) == expected, ('changed figure table', fig, name)
    report = {'passed': True, 'run_id': lock['run_id'], 'figures': figures,
              'outputs_and_source_tables_verified': True, 'documented_code_relocations': relocated}
    target = ROOT/'audit_archive/figure_refresh_20261026/figure_provenance_verification.json'
    target.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
