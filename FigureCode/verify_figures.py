"""Read-only verification of approved, pending and frozen figure outputs."""
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import Counter
import csv
import json
import importlib.util
import sys
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'FigureCode/_shared'))
from managed import code_hashes, paths_for, sha, verify_sources
from result_paths import relocated, verify_code, verify_digest, manifest_path, artifact_path, receipt


def verify_manifest(figure, state, current, profile, legacy, relocations, working_snapshot=True):
    folder = paths_for(figure, state)[0]
    manifest = relocated(json.loads(manifest_path(figure).read_text()))
    if not current:
        assert manifest['source'] == legacy, (figure, state, 'source')
    elif working_snapshot:
        assert manifest['source'] == profile, (figure, state, 'source')
    for item in manifest['source']['files'].values():
        assert sha(ROOT/item['path']) == item['sha256'], (figure, state, 'changed pinned input')
    if current:
        assert manifest['status'] == ('review' if state == 'review' else 'approved')
        if working_snapshot:
            verify_code(manifest['code'], code_hashes(ROOT/'FigureCode'/figure))
        assert all(Path(name).suffix in {'.png', '.pdf'} for name in manifest['outputs'])
        assert manifest['source_data_dir'] == str(paths_for(figure, state)[1].relative_to(ROOT))
    elif figure in {'Fig4', 'Fig5', 'ExtendedDataFig3', 'ExtendedDataFig4'}:
        for name, expected in manifest['code'].items():
            verify_digest(name, expected)
    # A superseded formal image remains verifiable against its original build
    # record, even when the working source has advanced to a pending review.
    for name, expected in manifest['outputs'].items():
        if receipt().get('layout_cleanup',{}).get('retired_outputs',{}).get(figure,{}).get(name)==expected:
            continue
        assert sha(artifact_path(figure,name)) == expected, (figure, state, name, 'changed output')
        if current and Path(name).suffix == '.pdf':
            document = PdfReader(artifact_path(figure,name))
            assert len(document.pages) == 1
            assert len(document.pages[0].extract_text()) > 100, (figure, state, name, 'blank or non-editable PDF')
    data = ROOT/manifest['source_data_dir']
    for name, expected in manifest['source_data'].items():
        assert sha(data/name) == expected, (figure, state, name, 'changed table')
    from preparation import preparation_path, verify_prepared
    extra = set()
    if preparation_path(figure).exists():
        prepared = verify_prepared(figure)
        assert not prepared['images_require_update'], (figure, 'prepared data changed; image requires update')
        extra = set(prepared['source_data']) - set(manifest['source_data'])
    if current:
        assert {str(p.relative_to(data)) for p in data.rglob('*') if p.is_file()} == set(manifest['source_data']) | extra
        if figure == 'ExtendedDataFig1':
            assert manifest['qa']['alignment']['passed']
    return manifest


def read_table(path):
    def value(cell):
        try:
            return Decimal(cell)
        except InvalidOperation:
            return cell
    with path.open(newline='') as stream:
        return [[value(cell) for cell in row] for row in csv.reader(stream)]


def verify_unchanged_evidence(figure, manifest, legacy):
    before = ROOT/legacy['figure_data_dir']/figure
    after = ROOT/manifest['source_data_dir']
    names = sorted(n for n in manifest['source_data'] if n != 'plot_data.rds')
    csv_count = 0
    for name in names:
        if Path(name).suffix == '.csv':
            assert read_table(before/name) == read_table(after/name), (figure, name, 'evidence changed')
            csv_count += 1
        elif Path(name).suffix == '.json':
            assert json.loads((before/name).read_text()) == json.loads((after/name).read_text()), (figure, name, 'evidence changed')
        else:
            assert sha(before/name) == sha(after/name), (figure, name, 'evidence changed')
    return csv_count


def verify_policy(profile):
    policy = json.loads((ROOT/profile['policy']['path']).read_text())
    # Independently express the agreed rule, checking all 289 H/E combinations.
    def level(h, e):
        if min(h, e) >= 12: return 1
        if max(h, e) >= 12 and min(h, e) >= 8: return 2
        if max(h, e) >= 12 or min(h, e) >= 8: return 3
        if max(h, e) >= 8: return 4
        return 5
    def label(score):
        return sum(score >= cut for cut in policy['cutpoints'])
    for h in range(17):
        for e in range(17):
            assert policy['level_matrix_L_M_H_vH'][label(h)][label(e)] == level(h, e)
    counts = Counter()
    with (ROOT/profile['files']['publication']['path']).open(newline='') as stream:
        for row in csv.DictReader(stream):
            h, e = (int(row[f'{domain}_score']) for domain in ['Hazard', 'Exposure'])
            for domain, score in [('Hazard', h), ('Exposure', e)]:
                assert Decimal(row[f'{domain}_score_raw']).quantize(Decimal('1'), rounding=ROUND_HALF_UP) == score
            assert Decimal(row['Priority_score']) == h+e
            counts[level(h, e)] += 1
    assert [counts[i] for i in range(1, 6)] == policy['expected_counts']
    return dict(sorted(counts.items()))


def main():
    profile = verify_sources()
    legacy = json.loads((ROOT/'FigureCode/figure_sources.json').read_text())
    for item in legacy['files'].values():
        assert sha(ROOT/item['path']) == item['sha256'], ('legacy source', item['path'])
    full_catalog = json.loads((ROOT/'FigureCode/catalog.json').read_text())
    catalog = full_catalog['figures']
    ledger = ROOT/'audit_archive/workspace_migration_20261026/code_relocations.json'
    relocations = json.loads(ledger.read_text()) if ledger.exists() else {}
    report = {'passed': True, 'run_id': profile['run_id'], 'level_counts': verify_policy(profile), 'figures': {}}
    for figure, item in catalog.items():
        state = 'review' if item['review'] else 'output'
        manifest = verify_manifest(figure,state,item['review'] or item['formal']=='current',profile,legacy,relocations)
        record = {'formal':item['formal'],'review':item['review']}
        if (item['review'] or item['formal'] == 'current') and figure in {'Fig2', 'ExtendedDataFig1', 'ExtendedDataFig2'}:
            record['unchanged_evidence_tables'] = verify_unchanged_evidence(figure, manifest, legacy)
        if figure == 'Fig4' and item['formal'] == 'current' and not item['review'] and item.get('publication_mode') == 'approved_asset_import':
            assert item.get('publication_mode') == 'approved_asset_import'
            spec = importlib.util.spec_from_file_location('fig4_approved', ROOT/'FigureCode/Fig4/verify.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            record['approved_composition'] = module.verify_publication(manifest)
        report['figures'][figure] = record
    report['supplementary'] = {}
    for name,item in full_catalog.get('supplementary',{}).items():
        from preparation import preparation_path, verify_prepared
        if preparation_path(name).exists():
            assert not verify_prepared(name)['images_require_update'], (name,'prepared data changed; image requires update')
        spec=importlib.util.spec_from_file_location('si_verification',ROOT/item['entrypoint'])
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        states={}
        if item['formal']=='current' and not item['review']:states['output']=module.verify('output',working=False)
        if item['review']:states['review']=module.verify('review',working=True)
        report['supplementary'][name]=states
    expected=set()
    for name in catalog:
        record=json.loads(manifest_path(name).read_text())
        expected.update(n for n in record['outputs'] if Path(n).suffix in {'.png','.pdf','.xlsx'})
    for name in full_catalog.get('supplementary',{}):
        expected.update(json.loads(manifest_path(name).read_text())['outputs'])
    for name in ['Level1Identity','Level1IdentityTree']:
        record=json.loads(manifest_path(name).read_text())
        for filename,digest in record['output_hashes'].items():
            if Path(filename).suffix in {'.png','.pdf'} and '.preview.' not in filename:
                assert sha(ROOT/'result/figures'/filename)==digest
                expected.add(filename)
    # Separately authorised explorations are verified, never promoted or added
    # to the manuscript deck. Only explicitly registered files are accepted.
    report['exploratory'] = {}
    for name,item in full_catalog.get('exploratory',{}).items():
        record = json.loads(manifest_path(name).read_text())
        assert record['status'] == 'exploratory_review', (name,'unexpected status')
        for source,digest in record['source_hashes'].items():
            assert sha(ROOT/source) == digest, (name,'changed source',source)
        for source,digest in record['code'].items():
            assert sha(ROOT/source) == digest, (name,'changed code',source)
        for filename,digest in record['outputs'].items():
            assert sha(artifact_path(name,filename)) == digest, (name,'changed output',filename)
            if Path(filename).suffix in {'.png','.pdf'}: expected.add(filename)
        data=ROOT/'result/figure_data'/name
        assert {str(p.relative_to(data)) for p in data.rglob('*') if p.is_file()} == set(record['source_data'])
        for filename,digest in record['source_data'].items():
            assert sha(data/filename) == digest, (name,'changed table',filename)
        assert set(item['files']) <= set(record['outputs']), (name,'unrecorded export')
        report['exploratory'][name] = {'verified':True,'included_in_ppt':False}
    for ext in ['png','pdf']:
        name='Sensitivity_analysis.'+ext
        assert sha(ROOT/'result/figures'/name)==sha(ROOT/'audit_archive/figure_maintenance/fig4_level1_adoption/legacy/output'/('Fig4.'+ext))
        expected.add(name)
    assert {p.name for p in (ROOT/'result/figures').iterdir() if p.name!='.DS_Store'}==expected, 'Unexpected or missing figure files'
    assert not list((ROOT/'FigureCode').glob('*/.building-*')), 'Incomplete figure build'
    assert not list((ROOT/'result/figures').glob('*/.building-*')), 'Incomplete table build'
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
