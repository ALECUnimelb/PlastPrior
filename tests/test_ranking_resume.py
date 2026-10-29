"""Resume real ranking and export from verified synthetic Stage 7A files."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior import priority, ranking
from plastprior.lrtp import VALUE_COLUMNS
from plastprior.resume_ranking import resume_ranking
from test_export import fixture, write_csv, sha
from test_priority import row_fixture


class RankingResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / '.result-work'
        self.work = self.workspace / 'work'
        self.work.mkdir(parents=True)
        rows = fixture(self.work)
        shutil.rmtree(self.work / 'stage7' / '7b')
        self.output = self.root / 'result'
        qsar = json.loads(Path(ranking.__file__).with_name('qsar_models.json').read_text(encoding='utf-8'))
        model_fields = [c for c in qsar['legacy_merge_columns'] if not c.startswith('Basic | ')]
        for row in rows:
            row.update(dict.fromkeys([*model_fields, *VALUE_COLUMNS], ''))
            row.update(row_fixture())
            row.update(qsar_evidence_available='False', lrtp_available='False')
            row['Persistence_score'] = '1' if row['inchikey'] in ('a', 'b') else '0'
            if row['inchikey'] == 'missing':
                for field in priority.HAZARD:
                    stem = field.removesuffix('_score').lower()
                    row.update({field: '', stem + '_available': 'False', stem + '_unavailable_reason': 'missing'})
                for field in priority.EXPOSURE:
                    row.update({'Exposure_' + field + '_score': '', 'exposure_' + field + '_available': 'False',
                                'exposure_' + field + '_unavailable_reason': 'missing'})
                row['Exposure_complete'] = 'False'
            row.update({k: '' if v is None else str(v) for k, v in priority.analysis_scores(row).items()})
        self.upstream = self.work / 'stage7' / '7a'
        write_csv(self.upstream / 'compound_priority_assessment.csv', list(rows[0]), rows)
        self.history = pd.DataFrame([{'inchikey': row['inchikey'], 'Priority_score': '2',
                                     'result_role': 'historical_reproduction_only'} for row in rows])
        write_csv(self.upstream / 'priority_historical.csv', list(self.history), self.history.to_dict('records'))
        (self.upstream / 'identity_review_source_links.jsonl').write_bytes(b'')
        self.manifest_path = self.upstream / 'priority_manifest.json'
        self.manifest = {'stage': '7A', 'ranking_computed': False,
                         'implementation_sha256': sha(Path(priority.__file__)),
                         'policy_sha256': sha(priority.POLICY_PATH),
                         'upstream_manifest_sha256': sha(self.work / 'stage6' / '6b' / 'exposure_scoring_manifest.json'),
                         'output_sha256': {p.name: sha(p) for p in self.upstream.iterdir() if p != self.manifest_path}}
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')
        policy = deepcopy(ranking.POLICY)
        policy['historical']['input_order_sha256'] = hashlib.sha256(('\n'.join(self.history['inchikey']) + '\n').encode()).hexdigest()
        policy['historical']['top100_order_sha256'] = '0' * 64
        patcher = patch.object(ranking, 'POLICY', policy)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_resume_exports_complete_paired_results_despite_legacy_order_mismatch(self):
        package = resume_ranking(self.workspace, self.output, top_n=1, progress=lambda _: None)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(package['compounds'], 4)
        for key in ('csv', 'sqlite', 'dashboard_sqlite'):
            self.assertTrue(package[key].is_file())
        with closing(sqlite3.connect(package['sqlite'])) as db:
            meta = json.loads(db.execute("SELECT value_json FROM run_metadata WHERE key='historical_order'").fetchone()[0])
            self.assertEqual(meta['mode'], 'portable')
            self.assertFalse(meta['frozen_top100_order_matches'])
            self.assertEqual(db.execute('SELECT inchikey FROM top_priority ORDER BY inchikey').fetchall(), [('a',), ('b',)])
        with closing(sqlite3.connect(package['dashboard_sqlite'])) as db:
            self.assertEqual(dict(db.execute('SELECT key,value FROM metadata'))['csv_sha256'], sha(package['csv']))
        self.assertFalse(list(self.root.glob('.*lock')))

    def test_strict_failure_leaves_stage7a_and_existing_results_untouched(self):
        before = {p: sha(p) for p in self.work.rglob('*') if p.is_file()}
        self.output.mkdir(); (self.output / 'evidence.txt').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'strict historical mode'):
            resume_ranking(self.workspace, self.output, strict_historical=True, progress=lambda _: None)
        self.assertEqual(before, {p: sha(p) for p in self.work.rglob('*') if p.is_file()})
        self.assertEqual((self.output / 'evidence.txt').read_bytes(), b'keep')
        self.assertFalse((self.work / 'stage7' / '7b').exists())

    def test_changed_upstream_file_still_blocks_resume_before_ranking(self):
        (self.work / 'stage4' / 'test_audit.jsonl').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'fingerprint differs'):
            resume_ranking(self.workspace, self.output, progress=lambda _: None)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.work / 'stage7' / '7b').exists())

    def test_inconsistent_current_scores_still_block_ranking(self):
        path = self.upstream / 'compound_priority_assessment.csv'
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame.loc[frame['inchikey'] == 'a', 'Priority_score'] = '25'
        write_csv(path, list(frame), frame.to_dict('records'))
        self.manifest['output_sha256'][path.name] = sha(path)
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'aggregate is inconsistent'):
            resume_ranking(self.workspace, self.output, progress=lambda _: None)
        self.assertFalse(self.output.exists())

    def test_historical_mode_cannot_change_current_ranks_or_membership(self):
        portable = ranking.integrate_ranking(self.upstream, top_n=1)
        legacy = self.history.assign(_score=2).sort_values('_score', ascending=False, kind='quicksort')
        ranking.POLICY['historical']['top100_order_sha256'] = hashlib.sha256(('\n'.join(legacy['inchikey']) + '\n').encode()).hexdigest()
        strict = ranking.integrate_ranking(self.upstream, top_n=1, strict_historical=True)
        for name in ('compound_rankings', 'eligible_priority_ranking', 'top_priority_including_ties', 'unranked_review'):
            pd.testing.assert_frame_equal(portable.tables[name], strict.tables[name])

    def test_portable_history_cannot_claim_frozen_regression_parity(self):
        from plastprior.ranking_validation import compare_ranking
        ranked = self.work / 'stage7' / '7b'
        ranking.integrate_ranking(self.upstream).write_reports(ranked)
        with patch('plastprior.priority_validation.compare_priority') as previous:
            report = compare_ranking(self.root / 'unavailable-baseline', ranked, self.root / 'validation')
        previous.assert_not_called()
        self.assertEqual(report['status'], 'failed')
        self.assertIn('strict_historical=True', (self.root / 'validation/ranking_differences.csv').read_text(encoding='utf-8'))
