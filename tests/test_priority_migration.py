"""Migration must permit only independently verified tier and policy changes."""
import csv
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plastprior.delivery import finish_run
from plastprior.priority_migration import verify_priority_migration, OLD_POLICY, NEW_POLICY


class PriorityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = self.root / 'old.csv'
        self.new = self.root / 'new.csv'
        self.rows = []
        for i, (h, e, old, new) in enumerate([
            ('10', '5', 'High priority', 'Moderate priority'),
            ('10.25', '5', 'High priority', 'High priority'),
            ('10', '4.5', 'High priority', 'Low priority'),
            ('11', '0', 'Low priority', 'Moderate priority')]):
            self.rows.append(dict(inchikey=str(i), Hazard_score=h, Exposure_score=e,
                Priority_score=str(float(h)+float(e)), Priority_tier=old, Priority_data_status='Partial',
                priority_scoring_policy=OLD_POLICY, Ranking_eligible='True', Priority_rank=str(i+1),
                Priority_tie_size='1', Top_n_selected='True', evidence='', expected_new=new))
        self.before = [{k: v for k, v in r.items() if k != 'expected_new'} for r in self.rows]
        self.after = [{**r, 'Priority_tier': self.rows[i]['expected_new'], 'priority_scoring_policy': NEW_POLICY}
                      for i, r in enumerate(self.before)]
        self.write(self.old, self.before)
        self.write(self.new, self.after)

    def write(self, path, rows):
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    def test_valid_migration(self):
        report = verify_priority_migration(self.old, self.new)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['changed_field_counts']['Priority_tier'], 3)
        self.assertEqual(report['top_n_count'], 4)

    def test_scores_ranks_top_n_missingness_and_evidence_cannot_change(self):
        for field, value in [('Hazard_score', '11'), ('Priority_score', '0'),
                             ('Priority_rank', '99'), ('Priority_tie_size', '2'),
                             ('Top_n_selected', 'False'), ('Priority_data_status', 'Complete'),
                             ('evidence', '0')]:
            rows = deepcopy(self.after); rows[0][field] = value
            self.write(self.new, rows)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Unexpected migration change'):
                verify_priority_migration(self.old, self.new)

    def test_incorrect_tier_cannot_hide_behind_allowed_field(self):
        rows = deepcopy(self.after); rows[0]['Priority_tier'] = 'High priority'
        self.write(self.new, rows)
        with self.assertRaisesRegex(ValueError, 'classification mismatch'):
            verify_priority_migration(self.old, self.new)

    def test_invalid_baseline_is_rejected(self):
        rows = deepcopy(self.before); rows[0]['Priority_tier'] = 'Low priority'
        self.write(self.old, rows)
        with self.assertRaisesRegex(ValueError, 'classification mismatch'):
            verify_priority_migration(self.old, self.new)

    def test_universe_and_versions_are_fixed(self):
        rows = deepcopy(self.after); rows[0]['inchikey'] = 'other'
        self.write(self.new, rows)
        with self.assertRaisesRegex(ValueError, 'universe'):
            verify_priority_migration(self.old, self.new)
        rows = deepcopy(self.after); rows[0]['priority_scoring_policy'] = 'unapproved'
        self.write(self.new, rows)
        with self.assertRaisesRegex(ValueError, 'Unsupported policy'):
            verify_priority_migration(self.old, self.new)

    def test_migration_failure_prevents_publication(self):
        archive = self.root / 'archive'; work = archive / 'run' / 'work'
        work.mkdir(parents=True); package_dir = work.parent / 'package'; package_dir.mkdir()
        rows = deepcopy(self.after); rows[0]['Priority_rank'] = '99'; self.write(self.new, rows)
        with patch('plastprior.export.export_results', return_value={'directory': package_dir, 'csv': self.new}), patch('plastprior.delivery.publish_daily') as publish:
            with self.assertRaisesRegex(ValueError, 'Unexpected migration change'):
                finish_run(work, self.root / 'new-results', archive, priority_migration_baseline=self.old)
            publish.assert_not_called()
        self.assertTrue(work.exists())

    def test_failed_migration_preserves_existing_current_directory(self):
        archive = self.root / 'archive'; work = archive / 'run' / 'work'; work.mkdir(parents=True)
        existing = self.root / 'existing'; existing.mkdir()
        previous = existing / 'PlastPrior_results.csv'
        previous.write_bytes(self.old.read_bytes())
        package_dir = work.parent / 'package'; package_dir.mkdir()
        rows = deepcopy(self.after); rows[0]['Priority_rank'] = '99'; self.write(self.new, rows)
        with patch('plastprior.export.export_results', return_value={'directory': package_dir, 'csv': self.new}), patch('plastprior.delivery.publish_daily') as publish:
            with self.assertRaisesRegex(ValueError, 'Unexpected migration change'):
                finish_run(work, existing, archive, priority_migration_baseline=self.old)
            publish.assert_not_called()
        self.assertEqual(previous.read_bytes(), self.old.read_bytes())
        self.assertTrue(work.exists())
