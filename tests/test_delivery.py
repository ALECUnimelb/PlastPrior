"""Daily-pair publication must preserve old results and stop on scientific drift."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plastprior.delivery import publish_daily, compare_csv, DAILY_NAMES
from plastprior.export import export_results
from test_export import fixture


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / 'audit_archive'
        self.archive.mkdir()
        work = self.archive / 'run' / 'work'
        work.mkdir(parents=True)
        fixture(work)
        self.package = export_results(work, work.parent / 'package')
        self.results = self.root / 'results'

    def test_legacy_directory_preserved_and_only_pair_visible(self):
        self.results.mkdir()
        (self.results / 'important.txt').write_text('old evidence')
        manifest = publish_daily(self.package, self.results, self.archive)
        self.assertTrue(self.results.is_symlink())
        self.assertEqual({p.name for p in self.results.iterdir()}, set(DAILY_NAMES))
        old = next(self.archive.glob('legacy-results-*'))
        self.assertEqual((old / 'important.txt').read_text(), 'old evidence')
        self.assertEqual(len(manifest['daily_files']), 2)

    def test_regression_blocks_publication_and_preserves_previous_directory(self):
        self.results.mkdir()
        baseline = self.results / DAILY_NAMES[0]
        baseline.write_bytes(self.package['csv'].read_bytes().replace(b'2.0', b'3.0'))
        with self.assertRaisesRegex(ValueError, 'Publication regression'):
            publish_daily(self.package, self.results, self.archive)
        self.assertFalse(self.results.is_symlink())
        self.assertTrue(baseline.exists())
        self.assertFalse((self.package['directory'] / 'daily').exists())

    def test_pointer_failure_restores_legacy_directory(self):
        self.results.mkdir()
        (self.results / 'evidence').write_text('preserve')
        with patch('plastprior.delivery.os.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                publish_daily(self.package, self.results, self.archive)
        self.assertEqual((self.results / 'evidence').read_text(), 'preserve')
        self.assertFalse(list(self.root.glob('.results-*.tmp')))

    def test_comparison_preserves_missing_zero_and_ties(self):
        result = compare_csv(self.package['csv'], self.package['csv'])
        self.assertEqual(result['changed_values'], 0)
        self.assertEqual(result['rows'], 4)

    def test_wrong_pair_is_rejected_before_migration(self):
        self.package['csv'].write_bytes(self.package['csv'].read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            publish_daily(self.package, self.results, self.archive)
        self.assertFalse(self.results.exists())

    def test_second_generation_switches_both_files_and_retains_old_package(self):
        publish_daily(self.package, self.results, self.archive)
        old = self.results.resolve()
        work = self.archive / 'second' / 'work'
        work.mkdir(parents=True)
        fixture(work)
        second = export_results(work, work.parent / 'package')
        manifest = publish_daily(second, self.results, self.archive)
        self.assertNotEqual(self.results.resolve(), old)
        self.assertTrue(all((old / name).exists() for name in DAILY_NAMES))
        self.assertEqual(manifest['regression']['changed_values'], 0)


if __name__ == '__main__':
    unittest.main()
