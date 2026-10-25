"""Source occurrence preservation, scientific invariance, and immutable refresh."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from plastprior.export import export_results, MANIFESTS
from plastprior.source_details import refresh_browser_projection
from test_export import fixture, write_csv, sha


class SourceDetailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'work'
        self.root.mkdir()
        fixture(self.root)

    def edit(self, relative, transform):
        path = self.root / relative
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        transform(rows)
        write_csv(path, fields, rows)
        for parts in MANIFESTS:
            manifest = self.root.joinpath(*parts)
            if manifest.parent == path.parent:
                data = json.loads(manifest.read_text())
                data['output_sha256'][path.name] = sha(path)
                manifest.write_text(json.dumps(data))

    def test_occurrences_and_distinct_source_tables_survive_same_identifiers(self):
        additions = [('extra1', 'plastchem'), ('extra2', 'fcchumon_s1'), ('extra3', 'fcchumon_s2')]
        def extend(rows):
            template = next(r for r in rows if r['record_id'] == 'source-a')
            for number, (identifier, table) in enumerate(additions, 10):
                rows.append(dict(template, record_id=identifier, table_id=table,
                                 source_record_number=str(number)))
        self.edit('stage2/source_records.csv', extend)
        self.edit('stage2/resolved_records.csv', extend)
        self.edit('stage2/compound_memberships.csv', lambda rows: rows.extend(
            dict(inchikey='a', record_id=identifier, is_representative='False') for identifier, _ in additions))
        self.edit('stage7/7b/compound_rankings.csv', lambda rows: [
            r.update(source_tables_json='["plastchem","fcchumon_s1","fcchumon_s2"]')
            for r in rows if r['inchikey'] == 'a'])
        package = export_results(self.root)
        with sqlite3.connect(package['dashboard_sqlite']) as db:
            value = db.execute("SELECT source_info_json FROM compound_audit WHERE inchikey_std='a'").fetchone()[0]
        records = json.loads(value)
        self.assertEqual(len(records), 4)
        self.assertEqual({r['source_db'] for r in records}, {'PlastChem', 'FCChumon S1', 'FCChumon S2'})
        self.assertTrue(all(r['Name'] == 'NA' and r['CAS'] == '001-01-1' and r['Smile'] == '' for r in records))
        self.assertTrue(all('confidence_level' not in r for r in records))
        self.assertEqual(sum(r['is_representative'] for r in records), 1)

    def test_wrong_resolved_identity_blocks_export(self):
        self.edit('stage2/resolved_records.csv', lambda rows: rows[0].update(inchikey='wrong'))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            export_results(self.root)

    def test_missing_resolution_blocks_export(self):
        self.edit('stage2/resolved_records.csv', lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, 'Missing resolved'):
            export_results(self.root)

    def test_reported_identifier_cannot_be_replaced_by_resolved_value(self):
        self.edit('stage2/resolved_records.csv', lambda rows: rows[0].update(name_reported='substituted'))
        with self.assertRaisesRegex(ValueError, 'Reported source identifier changed'):
            export_results(self.root)

    def test_refresh_preserves_csv_scientific_fields_and_original_files(self):
        package = export_results(self.root)
        # Simulate the existing browser generation lacking optional source details.
        with sqlite3.connect(package['dashboard_sqlite']) as db:
            db.execute('ALTER TABLE compound_audit DROP COLUMN source_info_json')
            db.execute("DELETE FROM metadata WHERE key='source_details'")
        hashes = {key: sha(package[key]) for key in ('csv', 'sqlite', 'dashboard_sqlite')}
        refreshed = refresh_browser_projection(package['sqlite'], package['csv'], package['dashboard_sqlite'],
                                               self.root.parent / 'refreshed')
        self.assertEqual(hashes, {key: sha(package[key]) for key in hashes})
        self.assertEqual(sha(refreshed['csv']), hashes['csv'])
        self.assertEqual(refreshed['verification']['changed_existing_values'], 0)
        self.assertEqual(refreshed['verification']['source_details']['linked_records'], 4)
        with sqlite3.connect(refreshed['dashboard_sqlite']) as db:
            self.assertEqual(db.execute("SELECT Priority_score,Priority_rank FROM compound_audit WHERE inchikey_std='missing'").fetchone(), ('', ''))


if __name__ == '__main__':
    unittest.main()
