"""Reject corrupted inputs before an approved Fig4 asset publication."""
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import importlib.util
import json
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fig4_approved', ROOT/'FigureCode/Fig4/verify.py')
fig4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fig4)


class ApprovedDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        lock = json.loads((ROOT/'FigureCode/Fig4/approved_composition.json').read_text())
        for name, record in lock['tables'].items():
            shutil.copy2(ROOT/record['path'], self.folder/name)
        self.publication = ROOT/'result/PlastPrior_results.csv'

    def mutate(self, name, change):
        path = self.folder/name
        rows = fig4.read_rows(path)
        change(rows)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_approved_tables_pass(self):
        self.assertEqual(fig4.verify_tables(self.folder, self.publication)['panel_totals'], [101, 101, 101])

    def test_wrong_panel_count_is_rejected(self):
        self.mutate('use_counts.csv', lambda rows: rows[0].update(n='999'))
        with self.assertRaises(AssertionError):
            fig4.verify_tables(self.folder, self.publication)

    def test_modified_rank_is_rejected(self):
        self.mutate('compound_membership.csv', lambda rows: rows[0].update(Priority_rank='999'))
        with self.assertRaises(AssertionError):
            fig4.verify_tables(self.folder, self.publication)

    def test_duplicate_compound_is_rejected(self):
        self.mutate('compound_membership.csv', lambda rows: rows[1].update(rows[0]))
        with self.assertRaises(AssertionError):
            fig4.verify_tables(self.folder, self.publication)


if __name__ == '__main__':
    unittest.main()
