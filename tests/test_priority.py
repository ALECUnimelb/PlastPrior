"""Stage 7A aggregation boundaries and protection against missing-value imputation."""
import unittest
from decimal import Decimal

from plastprior.priority import (
    HAZARD, EXPOSURE, analysis_scores, historical_scores, score_value, tier, keyed, change_reasons,
)
import pandas as pd


def row_fixture():
    row = {'Exposure_score': '0', 'Exposure_complete': 'True'}
    for c in HAZARD:
        row[c] = '0'
        stem = c.removesuffix('_score').lower()
        row[stem + '_available'] = 'True'
        row[stem + '_unavailable_reason'] = ''
    for c in EXPOSURE:
        row['Exposure_' + c + '_score'] = '0'
        row['exposure_' + c + '_available'] = 'True'
        row['exposure_' + c + '_unavailable_reason'] = ''
    return row


class PriorityTests(unittest.TestCase):
    def test_dual_gates_and_exact_thresholds(self):
        for h, e, expected in [(4, 8, 'High priority'), (8, 4, 'High priority'),
                               (10, 2, 'Moderate priority'), (2, 4, 'Moderate priority'),
                               (4, 2, 'Moderate priority'), (16, 0, 'Low priority'),
                               (1, 10, 'Low priority'), (0, 0, 'Low priority')]:
            self.assertEqual(tier(h, e), expected)
        self.assertEqual(tier(Decimal('3.9999'), 9), 'Moderate priority')
        self.assertEqual(tier(4, Decimal('7.9999')), 'Moderate priority')
        self.assertEqual(tier(Decimal('1.9999'), 10), 'Low priority')
        self.assertEqual(tier(None, 10), 'No data')

    def test_supported_zero_is_complete_and_not_missing(self):
        result = analysis_scores(row_fixture())
        self.assertTrue(result['Priority_eligible'])
        self.assertEqual(result['Priority_score'], 0)
        self.assertEqual(result['Priority_tier'], 'Low priority')
        self.assertEqual(result['Priority_ineligibility_reasons'], '[]')

    def test_missing_hazard_does_not_become_zero(self):
        row = row_fixture()
        row.update(Persistence_score='', persistence_available='False',
                   persistence_unavailable_reason='identity_review_required_no_independent_or_curated_fallback')
        result = analysis_scores(row)
        self.assertEqual(result['Hazard_score'], result['Hazard_observed_score'])
        self.assertEqual(result['Priority_score'], result['Hazard_score'])
        self.assertEqual(result['Hazard_available_dimensions'], 3)
        self.assertEqual(result['Hazard_data_status'], 'Partial')
        self.assertIn('identity_review', result['Priority_missing_reasons'])
        self.assertEqual(historical_scores(row)['Hazard_score'], 0)

    def test_missing_exposure_preserves_complete_hazard(self):
        row = row_fixture()
        row.update(Exposure_score='0', Exposure_complete='False', Exposure_patent_score='',
                   exposure_patent_available='False', exposure_patent_unavailable_reason='query_error')
        result = analysis_scores(row)
        self.assertEqual(result['Hazard_score'], 0)
        self.assertEqual(result['Priority_score'], result['Hazard_score'])
        self.assertEqual(result['Priority_tier'], 'Low priority')
        self.assertIn('query_error', result['Priority_missing_reasons'])

    def test_hazard_observed_sum_never_renormalised(self):
        row = row_fixture()
        row.update(Persistence_score='2', Mobility_score='1', Bioaccumulation_score='1', Toxicity_score='2')
        self.assertEqual(analysis_scores(row)['Hazard_score'], 13)
        row.update(Toxicity_score='', toxicity_available='False', toxicity_unavailable_reason='no_usable_evidence')
        result = analysis_scores(row)
        self.assertEqual(result['Hazard_observed_score'], 7)
        self.assertEqual(result['Hazard_score'], result['Hazard_observed_score'])

    def test_all_missing_hazard_is_unavailable(self):
        row = row_fixture()
        for c in HAZARD:
            row[c] = ''
            stem = c.removesuffix('_score').lower()
            row[stem + '_available'] = 'False'
            row[stem + '_unavailable_reason'] = 'no_usable_evidence'
        result = analysis_scores(row)
        self.assertEqual(result['Hazard_data_status'], 'Unavailable')
        self.assertEqual(result['Hazard_observed_score'], 0)
        self.assertEqual(result['Hazard_score'], result['Hazard_observed_score'])
        self.assertEqual(historical_scores(row)['Hazard_data_status'], 'No data')

    def test_flags_totals_and_reasons_must_agree(self):
        for patch in [{'persistence_available': 'False'}, {'Exposure_complete': 'False'},
                      {'Exposure_score': '1'}, {'Exposure_score': ''},
                      {'Persistence_score': '', 'persistence_available': 'False'},
                      {'Exposure_patent_score': '', 'exposure_patent_available': 'False',
                       'Exposure_complete': 'False', 'Exposure_score': ''}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                analysis_scores({**row_fixture(), **patch})

    def test_invalid_scores_are_errors_not_missing(self):
        for value in ['NaN', 'Infinity', '-1', 'unknown', True, 2.1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                score_value(value)
        self.assertIsNone(score_value(''))
        self.assertEqual(score_value('0'), Decimal(0))

    def test_historical_contract_rejects_incomplete_exposure(self):
        with self.assertRaises(ValueError):
            historical_scores({**row_fixture(), 'Exposure_patent_score': ''})

    def test_unrelated_gic_or_model_values_do_not_add_points(self):
        row = row_fixture()
        first = analysis_scores(row)
        row.update(GIC_regulatory_status='listed', gic_name_review_required='True',
                   qsar_identity_status='review_required', LRTP_POV_days='999999')
        self.assertEqual(analysis_scores(row), first)

    def test_change_causes_only_reference_relevant_domains(self):
        old = row_fixture()
        row = {**old, 'Exposure_patent_score': '', 'exposure_patent_available': 'False',
               'exposure_patent_unavailable_reason': 'query_error', 'Exposure_score': '0', 'Exposure_complete': 'False'}
        result = analysis_scores(row)
        self.assertEqual(change_reasons(old, row, result, 'Hazard_data_status'),
                         ['availability_status_distinguishes_complete_partial_and_unavailable'])
        self.assertEqual(change_reasons(old, row, result, 'Exposure_score'),
                         ['upstream_exposure_eligibility_audit'])

    def test_identity_join_rejects_duplicates_and_changed_universe(self):
        for values in [['a', 'a'], ['a', 'c'], ['a', '']]:
            with self.assertRaises(ValueError):
                keyed(pd.DataFrame({'inchikey': values}), ['a', 'b'])
        result = keyed(pd.DataFrame({'inchikey': ['b', 'a']}), ['a', 'b'])
        self.assertEqual(result['inchikey'].tolist(), ['a', 'b'])


if __name__ == '__main__':
    unittest.main()
