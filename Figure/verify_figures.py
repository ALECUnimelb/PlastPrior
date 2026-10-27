"""Read-only verification of approved, pending and frozen figure outputs."""
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import Counter
import csv
import json
import sys
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Figure/_shared'))
from managed import code_hashes, paths_for, sha, verify_sources


def verify_manifest(figure, state, current, profile, legacy, relocations, working_snapshot=True):
    folder = ROOT/'Figure'/figure/state
    manifest = json.loads((folder/'manifest.json').read_text())
    if not current:
        assert manifest['source'] == legacy, (figure, state, 'source')
    elif working_snapshot:
        assert manifest['source'] == profile, (figure, state, 'source')
    for item in manifest['source']['files'].values():
        assert sha(ROOT/item['path']) == item['sha256'], (figure, state, 'changed pinned input')
    if current:
        assert manifest['status'] == ('review' if state == 'review' else 'approved')
        if working_snapshot:
            assert manifest['code'] == code_hashes(folder.parent), (figure, state, 'stale code')
        assert set(p.name for p in folder.iterdir()) == set(manifest['outputs']) | {'manifest.json'}
        assert all(Path(name).suffix in {'.png', '.pdf'} for name in manifest['outputs'])
        assert manifest['source_data_dir'] == str(paths_for(figure, state)[1].relative_to(ROOT))
    elif figure in {'Fig4', 'Fig5', 'ExtendedDataFig3', 'ExtendedDataFig4'}:
        for name, expected in manifest['code'].items():
            observed = sha(ROOT/name)
            if observed != expected:
                record = relocations.get(name, {})
                assert record.get('before_sha256') == expected and record.get('after_sha256') == observed, (figure, name, 'changed frozen code')
    # A superseded formal image remains verifiable against its original build
    # record, even when the working source has advanced to a pending review.
    for name, expected in manifest['outputs'].items():
        assert sha(folder/name) == expected, (figure, state, name, 'changed output')
        if current and Path(name).suffix == '.pdf':
            document = PdfReader(folder/name)
            assert len(document.pages) == 1
            assert len(document.pages[0].extract_text()) > 100, (figure, state, name, 'blank or non-editable PDF')
    data = ROOT/manifest['source_data_dir']
    for name, expected in manifest['source_data'].items():
        assert sha(data/name) == expected, (figure, state, name, 'changed table')
    if current:
        assert {str(p.relative_to(data)) for p in data.rglob('*') if p.is_file()} == set(manifest['source_data'])
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
    names = sorted(manifest['source_data'])
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
    legacy = json.loads((ROOT/'Figure/figure_sources.json').read_text())
    for item in legacy['files'].values():
        assert sha(ROOT/item['path']) == item['sha256'], ('legacy source', item['path'])
    catalog = json.loads((ROOT/'Figure/catalog.json').read_text())['figures']
    ledger = ROOT/'audit_archive/workspace_migration_20261026/code_relocations.json'
    relocations = json.loads(ledger.read_text()) if ledger.exists() else {}
    report = {'passed': True, 'run_id': profile['run_id'], 'level_counts': verify_policy(profile), 'figures': {}}
    for figure, item in catalog.items():
        # An approved snapshot keeps its own provenance while a newer review is
        # pending. Working code/policy must match the review, not both versions.
        manifest = verify_manifest(figure, 'output', item['formal'] == 'current', profile, legacy, relocations, working_snapshot=not item['review'])
        record = {'formal': item['formal'], 'review': item['review']}
        if item['review']:
            assert item['managed']
            manifest = verify_manifest(figure, 'review', True, profile, legacy, relocations)
        else:
            assert not (ROOT/'Figure'/figure/'review').exists(), (figure, 'unlisted review')
        if (item['review'] or item['formal'] == 'current') and figure in {'Fig2', 'ExtendedDataFig1', 'ExtendedDataFig2'}:
            record['unchanged_evidence_tables'] = verify_unchanged_evidence(figure, manifest, legacy)
        report['figures'][figure] = record
    assert not list((ROOT/'Figure').glob('*/.building-*')), 'Incomplete figure build'
    assert not list((ROOT/'output/figure_data').glob('*/.building-*')), 'Incomplete table build'
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
