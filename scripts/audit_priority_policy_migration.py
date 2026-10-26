"""Read-only full-population audit: scores, ranks, source evidence and history remain fixed."""
import argparse
from collections import Counter
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from plastprior.priority_migration import verify_priority_migration


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def compare_table(old, new, table, ignored=()):
    columns = [r[1] for r in old.execute(f'PRAGMA table_info("{table}")')]
    assert columns == [r[1] for r in new.execute(f'PRAGMA table_info("{table}")')], table
    columns = [c for c in columns if c not in ignored]
    select = ','.join('"' + c.replace('"', '""') + '"' for c in columns)
    query = f'SELECT {select} FROM "{table}" ORDER BY 1'
    a, b = old.execute(query), new.execute(query)
    count = 0; sha = hashlib.sha256()
    while True:
        ra, rb = a.fetchone(), b.fetchone()
        assert ra == rb, (table, count)
        if ra is None:
            break
        sha.update((json.dumps(ra, ensure_ascii=False) + '\n').encode())
        count += 1
    return {'rows': count, 'unchanged_columns': columns, 'sha256': sha.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True, help='Previous archive package directory')
    parser.add_argument('--candidate', type=Path, required=True, help='New archive package directory')
    parser.add_argument('--approved-preview', type=Path, required=True)
    parser.add_argument('--preserved-hashes', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old_csv = args.baseline / 'PlastPrior_results.csv'
    new_csv = args.candidate / 'PlastPrior_results.csv'
    report = verify_priority_migration(old_csv, new_csv)
    with new_csv.open() as stream:
        rows = list(csv.DictReader(stream))
    with args.approved_preview.open() as stream:
        preview = {r['inchikey']: r for r in csv.DictReader(stream)}
    assert {r['inchikey'] for r in rows} == preview.keys()
    scores = {r['inchikey']: Decimal(r['Priority_score']) for r in rows if r['Ranking_eligible'] == 'True'}
    groups = Counter(scores.values()); rank = {}; above = 0
    for value in sorted(groups, reverse=True):
        rank[value] = above + 1; above += groups[value]
    cutoff = sorted(scores.values(), reverse=True)[min(100, len(scores))-1]
    top = []
    for r in rows:
        p = preview[r['inchikey']]
        assert r['Priority_tier'] == p['preview_tier']
        for field in ['Hazard_score', 'Exposure_score', 'Priority_score']:
            assert Decimal(r[field]) == Decimal(p[field])
        if r['Ranking_eligible'] == 'True':
            score = scores[r['inchikey']]
            assert int(r['Priority_rank']) == rank[score]
            assert int(r['Priority_tie_size']) == groups[score]
            assert (r['Top_n_selected'] == 'True') == (score >= cutoff)
            if score >= cutoff:
                top.append(r['inchikey'])
    assert Counter(r['Priority_tier'] for r in rows) == {'High priority': 265, 'Moderate priority': 3414, 'Low priority': 11446}
    with connect(args.baseline / 'PlastPrior_results.sqlite') as old, connect(args.candidate / 'PlastPrior_results.sqlite') as new:
        assert new.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        report['archive_unchanged_tables'] = {table: compare_table(old, new, table, ignored)
            for table, ignored in [('compounds', ('Priority_tier', 'priority_scoring_policy')),
                                   ('historical_results', ()), ('source_records', ()),
                                   ('compound_memberships', ()), ('chemical_family_audit', ())]}
        report['new_run_id'] = json.loads(new.execute("SELECT value_json FROM run_metadata WHERE key='run_id'").fetchone()[0])
        assert json.loads(new.execute("SELECT value_json FROM run_metadata WHERE key='csv_sha256'").fetchone()[0]) == digest(new_csv)
        expected = list(new.execute('SELECT inchikey,Priority_tier,priority_scoring_policy FROM compounds ORDER BY inchikey'))
    with connect(args.candidate / 'dashboard/PlastPrior_dashboard.sqlite') as detail:
        assert detail.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert list(detail.execute('SELECT inchikey,Priority_tier,priority_scoring_policy FROM compound_audit ORDER BY inchikey')) == expected
        assert detail.execute("SELECT value FROM metadata WHERE key='csv_sha256'").fetchone()[0] == digest(new_csv)
    preserved = json.loads(args.preserved_hashes.read_text())
    for path, sha in preserved.items():
        assert digest(path) == sha, 'Previous file changed: ' + path
    report.update(approved_preview_matches=True, independent_ranking_passed=True,
                  top100_count=len(top), cutoff_score=str(cutoff), cutoff_tie_size=groups[cutoff],
                  top100_identity_sha256=hashlib.sha256('\n'.join(sorted(top)).encode()).hexdigest(),
                  old_files_verified=len(preserved), dashboard_pair_verified=True,
                  output_sha256={str(p.relative_to(args.candidate)): digest(p)
                                 for p in [new_csv, args.candidate/'PlastPrior_results.sqlite', args.candidate/'dashboard/PlastPrior_dashboard.sqlite']})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'archive_unchanged_tables'}, indent=2))


if __name__ == '__main__':
    main()
