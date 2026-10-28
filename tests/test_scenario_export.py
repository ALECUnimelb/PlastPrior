import csv
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch
from plastprior.scenario_export import export_scenario, sha
from plastprior.scoring_scenarios import COMPONENT_MAXIMA

class ExportTests(unittest.TestCase):
    def test_preserves_audit_and_builds_paired_current_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'baseline 中文 # 100%';source.mkdir()
            row={field:'0' for field in COMPONENT_MAXIMA}
            row.update(inchikey='A',Hazard_score='0.5',Exposure_score='0',Priority_score='0.5',Priority_tier='Low priority',Persistence_score='0.25')
            row['Name'] = '化合物 α'
            fields=list(row)
            csv_path=source/'PlastPrior_results.csv'
            with csv_path.open('w',encoding='utf-8',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerow(row)
            archive=source/'PlastPrior_results.sqlite'
            with closing(sqlite3.connect(archive)) as db, db:
                db.execute('CREATE TABLE compounds ('+','.join('"'+f+'" TEXT' for f in fields)+')')
                db.execute('INSERT INTO compounds VALUES ('+','.join('?' for _ in fields)+')',list(row.values()))
                db.execute('CREATE TABLE audit_records (evidence TEXT)');db.execute("INSERT INTO audit_records VALUES ('unchanged')")
            detail=source/'PlastPrior_dashboard.sqlite'
            with closing(sqlite3.connect(detail)) as db, db:
                db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT)')
                db.executemany('INSERT INTO metadata VALUES (?,?)',[('csv_sha256',sha(csv_path)),('run_id','baseline')])
                db.execute('CREATE TABLE compound_audit (inchikey_std TEXT,'+','.join('"'+f+'" TEXT' for f in fields)+')')
                db.execute('INSERT INTO compound_audit VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',['A',*row.values()])
                db.execute('CREATE TABLE data_dictionary (field TEXT PRIMARY KEY,specification_json TEXT)')
            before={p.name:sha(p) for p in source.iterdir()}
            connections = []
            connect = sqlite3.connect
            def track(*args, **kwargs):
                db = connect(*args, **kwargs)
                connections.append(db)
                return db
            output=root/'new'
            with patch('sqlite3.connect', side_effect=track):
                summary=export_scenario(source,output)
            self.addCleanup(lambda: [db.close() for db in connections])
            for db in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute('SELECT 1')
            with (output/csv_path.name).open(encoding='utf-8',newline='') as f:
                self.assertEqual(next(csv.DictReader(f))['Name'], '化合物 α')
            self.assertEqual(before,{p.name:sha(p) for p in source.iterdir()})
            self.assertEqual(summary['rows'],1)
            with closing(sqlite3.connect(output/archive.name)) as db, db:
                self.assertEqual(db.execute('SELECT Hazard_score FROM compounds').fetchone()[0],'0.5')
                self.assertEqual(db.execute('SELECT Hazard_score,Hazard_score_raw,Priority_level FROM current_compounds').fetchone(),('1','0.50','4'))
                self.assertEqual(db.execute('SELECT evidence FROM audit_records').fetchone()[0],'unchanged')
            with closing(sqlite3.connect(output/detail.name)) as db, db:
                meta=dict(db.execute('SELECT key,value FROM metadata'))
                self.assertEqual(meta['csv_sha256'],sha(output/csv_path.name))
            export_scenario(source,output)
            self.assertFalse(output.is_symlink())
            self.assertFalse(list(root.glob('.new-previous')))
            self.assertEqual(before,{p.name:sha(p) for p in source.iterdir()})
