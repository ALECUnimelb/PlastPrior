"""Test P/M decision boundaries, missingness, isolation and annotation independence."""

import json
import unittest

import pandas as pd

from plastprior.hazard import (
    INPUT_FIELDS, LRTP_COLUMNS, LRTP_CTD_LIMIT_KM,
    OPERA_KOC_COLUMNS, PERSISTENCE_VEGA_COLUMNS, SCORE_COLUMNS,
    _aligned_history, _compute_lrtp_mobility_from_row, _compute_opera_mobility_from_row,
    _compute_vega_p, _lrtp_ratio_to_mobility_score, _opera_logkoc_to_mobility_score,
    score_pm, scoring_inputs,
)


class HazardTests(unittest.TestCase):
    def row(self, review=False):
        return {**dict.fromkeys(INPUT_FIELDS, ''), 'inchikey': 'synthetic-full-key',
                'db_extract_info': '{}', 'qsar_identity_status': 'review_required' if review else 'exact_key_match',
                'qsar_identity_reason': 'formula_difference' if review else '',
                'qsar_evidence_available': not review, 'lrtp_available': not review}

    def score(self, row):
        result, audits = score_pm(pd.DataFrame([row]))
        return result.iloc[0], audits

    def test_persistence_adi_boundary_and_missing(self):
        a, b = PERSISTENCE_VEGA_COLUMNS['water']
        for adi, expected in [(0.49, None), (0.5, 2), ('', None)]:
            with self.subTest(adi=adi):
                score, _ = _compute_vega_p(pd.Series({a: 'vP (high reliability)', b: adi}))
                self.assertEqual(score, expected)

    def test_persistence_maximum_and_tie_order(self):
        row = self.row()
        for compartment, label in [('water', 'nP/P'), ('soil', 'vP'), ('sediment', 'vP')]:
            a, b = PERSISTENCE_VEGA_COLUMNS[compartment]
            row.update({a: label, b: 0.8})
        score, evidence = _compute_vega_p(pd.Series(row))
        self.assertEqual(score, 2)
        self.assertEqual(evidence['qsar_vega_irfmn']['aggregation']['picked_compartment'], 'soil')

    def test_unrecognized_persistence_is_missing(self):
        a, b = PERSISTENCE_VEGA_COLUMNS['water']
        score, _ = _compute_vega_p(pd.Series({a: 'unrecognised', b: 1}))
        self.assertIsNone(score)

    def test_aquatic_cutoffs(self):
        for value, expected in [(1.999, 2), (2, 1), (2.999, 1), (3, 0.5), (3.999, 0.5), (4, 0)]:
            with self.subTest(value=value):
                self.assertEqual(_opera_logkoc_to_mobility_score(value), expected)

    def test_opera_adi_boundary(self):
        for adi, expected in [(0.49, None), (0.5, 2), ('', None)]:
            score, _ = _compute_opera_mobility_from_row(pd.Series({OPERA_KOC_COLUMNS['logkoc']: 1, OPERA_KOC_COLUMNS['adi']: adi}))
            self.assertEqual(score, expected)

    def test_lrtp_ratio_cutoffs(self):
        for ratio, expected in [(0, 0), (0.2499, 0), (0.25, 0.5), (0.5, 1), (1, 2)]:
            with self.subTest(ratio=ratio):
                self.assertEqual(_lrtp_ratio_to_mobility_score(ratio), expected)

    def test_lrtp_requires_both_values_and_valid_status(self):
        row = {LRTP_COLUMNS['ctd']: LRTP_CTD_LIMIT_KM, LRTP_COLUMNS['te']: 0, LRTP_COLUMNS['status']: 'warning'}
        self.assertEqual(_compute_lrtp_mobility_from_row(pd.Series(row))[0], 2)
        for changed in [{LRTP_COLUMNS['te']: ''}, {LRTP_COLUMNS['status']: 'invalid'}]:
            self.assertIsNone(_compute_lrtp_mobility_from_row(pd.Series({**row, **changed}))[0])

    def test_mobility_maximum_preserves_tie_bases(self):
        row = self.row()
        row.update({OPERA_KOC_COLUMNS['logkoc']: 1, OPERA_KOC_COLUMNS['adi']: 1,
                    LRTP_COLUMNS['ctd']: LRTP_CTD_LIMIT_KM, LRTP_COLUMNS['te']: 0, LRTP_COLUMNS['status']: 'ok'})
        result, _ = self.score(row)
        self.assertEqual(result['Mobility_score'], 2)
        self.assertIn('aquatic(OPERA logKoc)', result['Mobility_score_basis'])
        self.assertIn('LRTP(OECD CTD/TE)', result['Mobility_score_basis'])

    def test_independent_zero_beats_curated(self):
        row = self.row()
        a, b = PERSISTENCE_VEGA_COLUMNS['water']
        row.update({a: 'nP', b: 1, OPERA_KOC_COLUMNS['logkoc']: 4, OPERA_KOC_COLUMNS['adi']: 1,
                    'db_extract_info': json.dumps({'hazard': {'P': {'PlastChem': [2]}, 'M': {'PlastChem': [2]}}})})
        result, _ = self.score(row)
        self.assertEqual(result['Persistence_score'], 0)
        self.assertEqual(result['Mobility_score'], 0)

    def test_curated_fraction_and_precedence(self):
        row = self.row()
        row['db_extract_info'] = json.dumps({'hazard': {'P': {'A': [2], 'PlastChem': [0.25]}, 'M': {'Z': [2], 'A': [0.25]}}})
        result, _ = self.score(row)
        self.assertEqual(result['Persistence_score'], 0.25)
        self.assertEqual(result['Mobility_score'], 0.25)
        self.assertEqual(result['Mobility_score_basis'], 'A')

    def test_missing_is_not_zero(self):
        result, _ = self.score(self.row())
        self.assertTrue(result[SCORE_COLUMNS].isna().all())

    def test_review_leak_fails_and_history_is_explicit(self):
        row = self.row(True)
        row[OPERA_KOC_COLUMNS['logkoc']] = 2
        row[OPERA_KOC_COLUMNS['adi']] = 1
        with self.assertRaisesRegex(ValueError, 'leaked'):
            self.score(row)
        history, _ = score_pm(pd.DataFrame([row]), historical=True)
        self.assertEqual(history.iloc[0]['Mobility_score'], 1)

    def test_review_preserves_reason_and_empty_scores(self):
        result, audits = self.score(self.row(True))
        self.assertTrue(result[SCORE_COLUMNS].isna().all())
        for field in ['Persistence_evidence', 'Mobility_evidence']:
            self.assertEqual(json.loads(result[field])['identity_review']['reason'], 'formula_difference')
        for rows in audits.values():
            self.assertEqual(rows[0]['identity_review']['prediction_exclusion_reason'], 'identity_review_required')

    def test_review_allows_independent_curated_fallback(self):
        row = self.row(True)
        row['db_extract_info'] = json.dumps({'hazard': {'P': {'PlastChem': [1]}, 'M': {'PlastChem': [0.25]}}})
        result, _ = self.score(row)
        self.assertEqual(result['Persistence_score'], 1)
        self.assertEqual(result['Mobility_score'], 0.25)
        self.assertTrue(pd.isna(result['LRTP_M_score']))

    def test_unavailable_lrtp_keeps_diagnostics(self):
        row = self.row()
        row.update({'lrtp_available': False, LRTP_COLUMNS['status']: 'missing', LRTP_COLUMNS['warning_flags']: 'missing_log_kaw'})
        result, _ = self.score(row)
        evidence = json.loads(result['Mobility_evidence'])['oecd_lrtp']
        self.assertEqual(evidence['input_status'], 'missing')
        self.assertEqual(evidence['warning_flags'], 'missing_log_kaw')

    def test_gic_and_norman_never_affect_scores_or_evidence(self):
        row = self.row()
        before, _ = self.score(row)
        row.update({'GIC_regulatory_listing_count': 1000, 'gic_name_review_required': True,
                    'gic_shared_identifier_tag_expansion': True, 'norman_prediction_available': True,
                    'db_extract_info': json.dumps({'regulatory': {'GIC': [2]}, 'analytical_detectability': {'LC': 1}, 'hazard': {'B': {'PlastChem': [2]}, 'T': {'PlastChem': [2]}}})})
        after, _ = self.score(row)
        pd.testing.assert_series_equal(before, after)

    def test_duplicate_or_blank_keys_fail(self):
        frame = pd.DataFrame([self.row(), self.row()])
        with self.assertRaisesRegex(ValueError, 'unique'):
            scoring_inputs(frame)
        frame = frame.iloc[:1].copy(); frame['inchikey'] = ''
        with self.assertRaisesRegex(ValueError, 'unique'):
            scoring_inputs(frame)

    def test_historical_join_uses_keys_and_rejects_missing(self):
        base = pd.DataFrame([self.row(), {**self.row(), 'inchikey': 'other'}])
        source = base.iloc[::-1].copy()
        source[OPERA_KOC_COLUMNS['logkoc']] = [2, 4]
        joined = _aligned_history(base, source, source)
        self.assertEqual(joined[OPERA_KOC_COLUMNS['logkoc']].tolist(), [4, 2])
        with self.assertRaisesRegex(ValueError, 'identity sets'):
            _aligned_history(base, source.iloc[:1], source)

    def test_unavailable_flags_mask_numeric_inputs(self):
        row = self.row()
        a, b = PERSISTENCE_VEGA_COLUMNS['water']
        row.update({a: 'vP', b: 1, OPERA_KOC_COLUMNS['logkoc']: 1, OPERA_KOC_COLUMNS['adi']: 1,
                    LRTP_COLUMNS['ctd']: LRTP_CTD_LIMIT_KM, LRTP_COLUMNS['te']: 0, LRTP_COLUMNS['status']: 'ok',
                    'qsar_evidence_available': False, 'lrtp_available': False})
        result, _ = self.score(row)
        self.assertTrue(result[SCORE_COLUMNS].isna().all())

    def test_invalid_availability_flag_fails(self):
        row = self.row(); row['lrtp_available'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'explicit booleans'):
            self.score(row)

    def test_nonfinite_numeric_inputs_fail(self):
        row = self.row(); row[OPERA_KOC_COLUMNS['logkoc']] = 'inf'
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            self.score(row)


if __name__ == '__main__':
    unittest.main()
