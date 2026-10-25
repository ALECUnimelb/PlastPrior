"""Compact publication packaging, provenance retention and failure isolation."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from plastprior.export import (
    MAIN_TABLES, MANIFESTS, SCORES, COUNTS, FLAGS, SUMMARY_FIELDS,
    _inventory, _value, archived_bytes, export_results, read_audit_payload, read_artifact_records,
)
from plastprior.publication import REQUIRED_FIELDS, FIELDS as PUBLICATION_FIELDS, project

INPUT_FIELDS = list(dict.fromkeys([*SUMMARY_FIELDS, *sorted(REQUIRED_FIELDS)]))


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root):
    rows = []
    # The source order deliberately differs from final rank order.
    for key, score, rank, eligible, selected in [
        ('missing', '', '', 'False', ''), ('b', '2.0', '1', 'True', 'True'),
        ('a', '2.0', '1', 'True', 'True'), ('zero', '0.0', '3', 'True', 'False'),
    ]:
        row = dict.fromkeys(INPUT_FIELDS, '')
        row.update({field: 'False' for field in FLAGS})
        row.update({field: '0' for field in COUNTS})
        row.update({field: score for field in SCORES})
        row.update(inchikey=key, name_resolved='NA', cas_reported='001-01-1',
                   smiles_isomeric='C', representative_record_id='source-' + key,
                   Priority_rank=rank, Priority_tie_size='2' if rank == '1' else ('1' if rank else ''),
                   Priority_eligible=eligible, Ranking_eligible=eligible, Top_n_selected=selected,
                   qsar_identity_status='review_required' if key == 'missing' else 'verified',
                   qsar_identity_reason='identity_review_required' if key == 'missing' else '',
                   gic_name_review_required='True' if key == 'missing' else 'False',
                   Ranking_exclusion_reasons='[{"domain":"hazard","dimension":"Persistence","reason":"missing_evidence"}]' if key == 'missing' else '[]',
                   source_tables_json='["plastchem","fccmigex"]',
                   exposure_human_biomonitoring_available='True',
                   Priority_data_status='Insufficient evidence' if key == 'missing' else 'Complete')
        rows.append(row)
    paths = {table: root.joinpath(*parts) for parts, table in MAIN_TABLES.items()}
    write_csv(paths['compounds'], INPUT_FIELDS, rows)
    write_csv(paths['historical_results'], ['inchikey', 'Historical_sort_position', 'Priority_score'],
              [{'inchikey': row['inchikey'], 'Historical_sort_position': str(i), 'Priority_score': '2.0'} for i, row in enumerate(rows, 1)])
    write_csv(paths['source_records'], ['record_id', 'source_id', 'reported_fields_json'],
              [{'record_id': 'source-' + row['inchikey'], 'source_id': 'test',
                'reported_fields_json': '{"Name":"NA"}'} for row in rows])
    write_csv(paths['compound_memberships'], ['inchikey', 'record_id', 'is_representative'],
              [{'inchikey': row['inchikey'], 'record_id': 'source-' + row['inchikey'],
                'is_representative': 'True'} for row in rows])
    ranked = [rows[2], rows[1], rows[3]]
    folder = root / 'stage7' / '7b'
    write_csv(folder / 'eligible_priority_ranking.csv', INPUT_FIELDS, ranked)
    write_csv(folder / 'top_priority_including_ties.csv', INPUT_FIELDS, ranked[:2])
    audits = root / 'stage4' / 'test_audit.jsonl'
    audits.parent.mkdir(parents=True)
    audits.write_text('{"inchikey":"missing","reason":"identity_review_required","value":null}\n'
                      '{"inchikey":"a","reason":"independent_evidence","nested":{"zero":0,"flag":false}}\n', encoding='utf-8')
    duplicate = audits.with_name('identical_audit.jsonl')
    duplicate.write_bytes(audits.read_bytes())
    for name in ['source_inventory.csv', 'table_dimensions.csv', 'supporting_inputs.csv']:
        write_csv(root / name, ['source', 'status'], [{'source': 'test', 'status': 'OK'}])
    for parts in MANIFESTS:
        path = root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        outputs = {p.name: sha(p) for p in path.parent.iterdir() if p.suffix in ('.csv', '.jsonl')}
        path.write_text(json.dumps({'output_sha256': outputs}) + '\n', encoding='utf-8')
    return rows


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'run'
        self.root.mkdir()
        self.rows = fixture(self.root)

    def test_round_trip_missing_zero_ties_flags_and_source_links(self):
        original = {p: sha(p) for p in self.root.rglob('*') if p.is_file()}
        package = export_results(self.root, self.root / 'final' / 'test')
        self.assertEqual(package['status'], 'passed')
        self.assertEqual(package['compounds'], 4)
        self.assertEqual(package['top_n_compounds'], 2)
        self.assertEqual({p.name for p in package['directory'].iterdir()},
                         {'PlastPrior_results.csv', 'PlastPrior_results.sqlite',
                          'PlastPrior_data_dictionary.csv', 'README.md', 'dashboard'})
        with package['csv'].open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r['inchikey'] for r in rows], ['a', 'b', 'zero', 'missing'])
        self.assertEqual(rows[-1]['Priority_score'], '')
        self.assertEqual(rows[2]['Priority_score'], '0.0')
        self.assertEqual(rows[0]['Name'], 'NA')
        self.assertEqual(rows[0]['CAS'], '001-01-1')
        self.assertEqual(rows[0]['source_dbs'], 'PlastChem; FCCmigex')
        self.assertEqual(list(rows[0]), list(PUBLICATION_FIELDS))
        self.assertEqual(rows[-1]['Ranking_exclusion_reasons'], 'hazard/Persistence: missing_evidence')
        with sqlite3.connect(package['dashboard_sqlite']) as detail:
            meta = dict(detail.execute('SELECT * FROM metadata'))
            self.assertEqual(meta['format'], 'plastprior-dashboard-v1')
            self.assertEqual(meta['csv_sha256'], sha(package['csv']))
            self.assertEqual(detail.execute("SELECT Name,Priority_score FROM compound_audit WHERE inchikey_std='missing'").fetchone(), ('NA', ''))
        with sqlite3.connect(package['sqlite']) as db:
            self.assertEqual(db.execute("SELECT Priority_score, Priority_rank, Top_n_selected FROM compounds WHERE inchikey='missing'").fetchone(), (None, None, None))
            self.assertEqual(db.execute("SELECT Priority_score, Top_n_selected FROM compounds WHERE inchikey='zero'").fetchone(), (0.0, 0))
            self.assertEqual(db.execute("SELECT qsar_identity_status,gic_name_review_required FROM compounds WHERE inchikey='missing'").fetchone(), ('review_required', 1))
            self.assertEqual(db.execute('SELECT inchikey FROM top_priority ORDER BY Priority_rank,inchikey').fetchall(), [('a',), ('b',)])
            self.assertEqual(db.execute('SELECT count(*) FROM compound_memberships').fetchone()[0], 4)
            evidence = db.execute("SELECT payload_id FROM evidence WHERE artifact_path='stage4/test_audit.jsonl' ORDER BY record_number").fetchall()
            self.assertIsNone(read_audit_payload(db, evidence[0][0])['value'])
            self.assertEqual(read_audit_payload(db, evidence[1][0])['nested'], {'zero': 0, 'flag': False})
            self.assertEqual(list(read_artifact_records(db, 'stage4/test_audit.jsonl')),
                             [json.loads(line) for line in (self.root / 'stage4' / 'test_audit.jsonl').read_text(encoding='utf-8').splitlines()])
            with self.assertRaisesRegex(ValueError, 'not original file bytes'):
                b''.join(archived_bytes(db, 'stage4/test_audit.jsonl'))
            self.assertEqual(b''.join(archived_bytes(db, 'stage4/evidence_manifest.json')),
                             (self.root / 'stage4' / 'evidence_manifest.json').read_bytes())
            digest = sha(self.root / 'stage4' / 'test_audit.jsonl')
            self.assertEqual(db.execute('SELECT count(*) FROM artifact_contents WHERE sha256=?', (digest,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM audit_records WHERE content_id=(SELECT id FROM artifact_contents WHERE sha256=?)', (digest,)).fetchone()[0], 2)
            metadata = dict(db.execute('SELECT key,value_json FROM run_metadata'))
            self.assertEqual(json.loads(metadata['csv_sha256']), sha(package['csv']))
        self.assertTrue(all(sha(p) == digest for p, digest in original.items()))

    def refresh_manifest(self, parts):
        path = self.root.joinpath(*parts)
        outputs = {p.name: sha(p) for p in path.parent.iterdir() if p.suffix in ('.csv', '.jsonl')}
        path.write_text(json.dumps({'output_sha256': outputs}), encoding='utf-8')

    def test_sparse_snapshot_retains_unique_fields_text_and_order(self):
        path = self.root / 'stage5' / 'compound_pm_hazard.csv'
        expected = [{'inchikey': 'b', 'Priority_score': '7.50', 'early_only': 'NA'},
                    {'inchikey': 'missing', 'Priority_score': '', 'early_only': '0'}]
        write_csv(path, ['inchikey', 'Priority_score', 'early_only'], expected)
        self.refresh_manifest(('stage5', 'hazard_manifest.json'))
        package = export_results(self.root)
        with sqlite3.connect(package['sqlite']) as db:
            self.assertEqual(list(read_artifact_records(db, 'stage5/compound_pm_hazard.csv')), expected)
            self.assertEqual(db.execute("SELECT disposition FROM artifacts WHERE path='stage5/compound_pm_hazard.csv'").fetchone()[0], 'final_values_plus_sparse_overrides')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT Priority_score FROM compounds WHERE inchikey='b'").fetchone()[0], 2)

    def test_top_n_covering_the_whole_pool_shares_snapshot_content(self):
        source = self.root / 'stage7' / '7b' / 'eligible_priority_ranking.csv'
        self.rows[3]['Top_n_selected'] = 'True'
        write_csv(source.parent / 'compound_rankings.csv', INPUT_FIELDS, self.rows)
        write_csv(source, INPUT_FIELDS, [self.rows[2], self.rows[1], self.rows[3]])
        (source.parent / 'top_priority_including_ties.csv').write_bytes(source.read_bytes())
        self.refresh_manifest(('stage7', '7b', 'ranking_manifest.json'))
        package = export_results(self.root)
        with sqlite3.connect(package['sqlite']) as db:
            paths = ['stage7/7b/eligible_priority_ranking.csv', 'stage7/7b/top_priority_including_ties.csv']
            self.assertEqual(list(read_artifact_records(db, paths[0])), list(read_artifact_records(db, paths[1])))

    def test_only_explicit_out_of_universe_patent_rows_are_omitted(self):
        path = self.root / 'stage6' / '6a' / 'pubchemlite_patent_records.jsonl'
        examples = [
            {'compound_key': 'outside', 'eligible': False, 'exclusion_reasons': ['outside_compound_universe']},
            {'compound_key': 'missing', 'eligible': False, 'exclusion_reasons': ['invalid_or_missing_count']},
            {'compound_key': 'a', 'eligible': True, 'exclusion_reasons': []},
            {'compound_key': 'other', 'eligible': False, 'exclusion_reasons': ['invalid_or_missing_count']},
        ]
        path.write_text(''.join(json.dumps(r)+'\n' for r in examples), encoding='utf-8')
        self.refresh_manifest(('stage6', '6a', 'exposure_manifest.json'))
        package = export_results(self.root)
        self.assertEqual(package['scope_omitted_records'], 1)
        with sqlite3.connect(package['sqlite']) as db:
            self.assertEqual(list(read_artifact_records(db, path.relative_to(self.root).as_posix())), examples[1:])
            self.assertEqual(db.execute("SELECT record_number,inchikey FROM evidence WHERE artifact_path='stage6/6a/pubchemlite_patent_records.jsonl' ORDER BY record_number").fetchall(), [(2,'missing'),(3,'a'),(4,'other')])
            self.assertEqual(db.execute('SELECT first_record,last_record FROM omitted_ranges').fetchall(), [(1,1)])

    def test_shared_bodies_keep_distinct_source_occurrences(self):
        path = self.root / 'stage4' / 'shared_audit.jsonl'
        body = {'long_evidence': 'preserved evidence ' * 100}
        examples = [{'compound_key': 'a', 'source_record_id': key, 'body': body, 'selected': False,
                     'selection_reason': 'not_selected'} for key in ['first', 'second']]
        path.write_text(''.join(json.dumps(r)+'\n' for r in examples), encoding='utf-8')
        self.refresh_manifest(('stage4', 'evidence_manifest.json'))
        package = export_results(self.root)
        with sqlite3.connect(package['sqlite']) as db:
            self.assertEqual(list(read_artifact_records(db, 'stage4/shared_audit.jsonl')), examples)
            self.assertEqual(db.execute("SELECT record_id,selected FROM evidence WHERE artifact_path='stage4/shared_audit.jsonl' ORDER BY record_number").fetchall(), [('first',0),('second',0)])
            self.assertEqual(db.execute("SELECT count(*) FROM evidence_payloads WHERE kind='value'").fetchone()[0], 1)

    def test_existing_destinations_and_stage_destinations_are_rejected(self):
        destination = self.root / 'existing'
        destination.mkdir()
        with self.assertRaises(FileExistsError):
            export_results(self.root, destination)
        with self.assertRaises(ValueError):
            export_results(self.root, self.root / 'stage2' / 'new')

    def test_changed_inputs_and_incomplete_runs_are_rejected(self):
        source = self.root / 'stage2' / 'source_records.csv'
        source.write_text('changed\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fingerprint differs'):
            export_results(self.root)
        self.assertFalse((self.root / 'final').exists())

    def test_missing_upstream_reference_is_rejected(self):
        path = self.root.joinpath(*MANIFESTS[-1])
        declaration = json.loads(path.read_text(encoding='utf-8'))
        declaration['upstream_manifest_sha256'] = '0' * 64
        path.write_text(json.dumps(declaration), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'upstream fingerprint'):
            _inventory(self.root.resolve())

    def test_failure_does_not_publish_a_partial_package(self):
        destination = self.root / 'final' / 'failed'
        with patch('plastprior.export._validate', side_effect=ValueError('validation failed')):
            with self.assertRaisesRegex(ValueError, 'validation failed'):
                export_results(self.root, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.iterdir()), [])

    def test_malformed_and_lossy_numeric_conversions_are_rejected(self):
        for value in ['NaN', 'inf', '-1', 'True', '0.1234567890123456789']:
            with self.assertRaises(ValueError):
                _value('Priority_score', value)
        for value in ['1.5', str(2**63)]:
            with self.assertRaises(ValueError):
                _value('Priority_rank', value)
        with self.assertRaises(ValueError):
            _value('Top_n_selected', 'unknown')
        self.assertIsNone(_value('Priority_score', ''))
        self.assertEqual(_value('Priority_score', '0'), 0)
        self.assertEqual(_value('cas_reported', '000-01-0'), '000-01-0')

    def test_publication_requires_fields_and_preserves_zero_and_unknown(self):
        row = dict(self.rows[3])
        row.update(Exposure_patent_count='0.0', Exposure_literature_count='',
                   Exposure_scale_reporting_period='', Exposure_scale_metric_type='import')
        result = project(row)
        self.assertEqual(result['Exposure_patent_count'], '0.0')
        self.assertEqual(result['Exposure_literature_count'], '')
        self.assertEqual(result['Exposure_scale_reporting_period'], '')
        self.assertEqual(result['Exposure_scale_metric_type'], 'import')
        del row['Exposure_patent_count']
        with self.assertRaisesRegex(ValueError, 'Missing publication inputs'):
            project(row)

    def test_publication_failure_does_not_publish_partial_package(self):
        destination = self.root / 'final' / 'bad-publication'
        with patch('plastprior.publication.write_publication', side_effect=ValueError('publication validation failed')):
            with self.assertRaisesRegex(ValueError, 'publication validation failed'):
                export_results(self.root, destination)
        self.assertFalse(destination.exists())

    def test_structural_annotations_reach_csv_and_both_databases_without_rescoring(self):
        smiles = 'Brc1c(Br)c(Br)c(Oc2c(Br)c(Br)c(Br)c(Br)c2Br)c(Br)c1Br'
        for path in (self.root / 'stage7' / '7b').glob('*.csv'):
            with path.open(newline='') as stream:
                reader = csv.DictReader(stream)
                fields, rows = reader.fieldnames, list(reader)
            if 'smiles_isomeric' in fields:
                for row in rows:
                    if row['inchikey'] == 'b':
                        row['smiles_isomeric'] = smiles
                write_csv(path, fields, rows)
        self.refresh_manifest(('stage7', '7b', 'ranking_manifest.json'))
        package = export_results(self.root)
        with package['csv'].open() as stream:
            row = next(r for r in csv.DictReader(stream) if r['inchikey'] == 'b')
        self.assertEqual(row['category_labels'], 'PBDE')
        self.assertEqual((row['Priority_score'], row['Priority_rank']), ('2.0', '1'))
        for database in (package['sqlite'], package['dashboard_sqlite']):
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute("SELECT category_labels,original_smiles FROM chemical_family_audit WHERE inchikey='b'").fetchone(), ('PBDE', smiles))
                self.assertEqual(db.execute("SELECT classification_status FROM chemical_family_audit WHERE inchikey='zero'").fetchone()[0], 'unclassified')


if __name__ == '__main__':
    unittest.main()
