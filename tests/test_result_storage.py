"""Result replacement preserves consistency and recovers from failed installs."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import os
from plastprior.result_storage import install_package, update_lock


class ResultStorageTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.result=self.root/'result';self.result.mkdir()
        self.package=self.root/'candidate';self.package.mkdir()
        (self.result/'PlastPrior_results.csv').write_text('old')
        (self.package/'PlastPrior_results.csv').write_text('new')
        (self.package/'PlastPrior_results.sqlite').write_bytes(b'new database')

    def test_replacement_keeps_required_baseline_and_removes_backup(self):
        (self.result/'baseline').mkdir();(self.result/'baseline/evidence').write_text('keep')
        install_package(self.package,self.result)
        self.assertEqual((self.result/'PlastPrior_results.csv').read_text(),'new')
        self.assertEqual((self.result/'figure_data/_dependencies/baseline/evidence').read_text(),'keep')
        self.assertFalse(self.result.is_symlink())
        self.assertFalse(list(self.root.glob('.result-*')))

    def test_failed_install_restores_old_directory(self):
        real=os.replace
        def fail_candidate(src,dst):
            if Path(src).name.startswith('.result-building-'):raise OSError('interrupted')
            return real(src,dst)
        with patch('plastprior.result_storage.os.replace',side_effect=fail_candidate):
            with self.assertRaises(OSError):install_package(self.package,self.result)
        self.assertEqual((self.result/'PlastPrior_results.csv').read_text(),'old')
        self.assertFalse((self.result/'PlastPrior_results.sqlite').exists())
        self.assertFalse(list(self.root.glob('.result-*')))

    def test_concurrent_update_cannot_enter(self):
        with update_lock(self.result):
            with self.assertRaises(RuntimeError):install_package(self.package,self.result)
        self.assertEqual((self.result/'PlastPrior_results.csv').read_text(),'old')

    def test_new_data_cannot_inherit_old_figure_tables(self):
        (self.result/'figures/Fig1/data').mkdir(parents=True)
        (self.result/'figures/Fig1/data/counts.csv').write_text('old counts')
        with self.assertRaisesRegex(ValueError,'coordinated refresh'):
            install_package(self.package,self.result)
        self.assertEqual((self.result/'PlastPrior_results.csv').read_text(),'old')
        self.assertEqual((self.result/'figures/Fig1/data/counts.csv').read_text(),'old counts')
        self.assertFalse(list(self.root.glob('.result-*')))

    def test_same_data_refresh_retains_current_figures(self):
        (self.package/'PlastPrior_results.csv').write_text('old')
        (self.result/'figures').mkdir();(self.result/'figures/image.png').write_bytes(b'figure')
        install_package(self.package,self.result)
        self.assertEqual((self.result/'figures/image.png').read_bytes(),b'figure')

    def test_same_csv_cannot_hide_changed_database_provenance(self):
        (self.package/'PlastPrior_results.csv').write_text('old')
        (self.result/'PlastPrior_results.sqlite').write_bytes(b'old database')
        (self.result/'figures').mkdir()
        with self.assertRaisesRegex(ValueError,'coordinated refresh'):
            install_package(self.package,self.result)
        self.assertEqual((self.result/'PlastPrior_results.sqlite').read_bytes(),b'old database')

    def test_project_inputs_and_retired_locations_are_not_destinations(self):
        project=Path(__file__).resolve().parents[1]
        for name in ['data','output','results','FigureCode']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'Project results'):
                install_package(self.package,project/name)
