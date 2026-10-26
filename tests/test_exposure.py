"""Scientific boundaries, missingness and source selection for Stage 6B."""
import unittest
from decimal import Decimal

import pandas as pd

from plastprior.exposure import (
    threshold_score, production_score, aggregate_components, select_patent,
    historical_input_view, human_detection_score, COMPONENTS, reference,
)


class ExposureScoreTests(unittest.TestCase):
    def test_discrete_threshold_boundaries(self):
        for dim, bands in [('inventory', [(1,.5),(2,1),(4,2)]),
                           ('patent', [(1,.5),(1000,1),(10000,2)]),
                           ('literature', [(1,.5),(5,1),(20,2)])]:
            previous = 0.0
            for cutoff, score in bands:
                self.assertEqual(threshold_score(Decimal(cutoff) - Decimal('0.0001'), dim), previous)
                self.assertEqual(threshold_score(cutoff, dim), score)
                previous = score
            self.assertEqual(threshold_score(0, dim), 0)
            for value in [None, '', 'unknown', -1, 'NaN', 'Infinity', True]:
                self.assertIsNone(threshold_score(value, dim))

    def test_production_numeric_and_qualitative_priority(self):
        for value, expected in [('0', 0), ('0.01', .5), ('999.999', .5), ('1000', 1), ('99999.999', 1), ('100000', 2)]:
            self.assertEqual(production_score(value, 'unknown'), expected)
        self.assertEqual(production_score(0, 'confirmed_confidential_quantity'), .5)
        self.assertEqual(production_score(None, 'historical_record'), .5)
        self.assertEqual(production_score(None, 'confirmed_zero_quantity'), 0)
        self.assertIsNone(production_score(None, 'not_found_in_source'))
        self.assertIsNone(production_score(-6, 'unknown'))
        self.assertEqual(production_score(None, 'confirmed_record_no_public_quantity'), .5)

    def test_unqueryable_or_ambiguous_human_evidence_is_not_zero(self):
        valid = {'policy_version': reference.FCCHUMON_HUMAN_DETECTION_POLICY_VERSION,
                 'match_method': 'no_match', 'target_cas_mapping_status': 'one_to_one', 'detected': False}
        self.assertEqual(human_detection_score(valid), (0.0, ''))
        self.assertIsNone(human_detection_score({**valid, 'target_cas_mapping_status': 'invalid_or_missing'})[0])
        self.assertIsNone(human_detection_score({**valid, 'match_method': 'cas_rejected_ambiguous_target_mapping'})[0])
        self.assertEqual(human_detection_score({**valid, 'match_method': 'exact_one_to_one_cas', 'detected': True})[0], 1)

    def test_total_retains_available_contributions_without_rescaling(self):
        values = {k: 0.0 for k in COMPONENTS}
        full = aggregate_components(values)
        self.assertEqual(full['Exposure_score'], 0)
        self.assertTrue(full['Exposure_complete'])
        values.update(food_contact=1, human_biomonitoring=1, production=2, patent=2, literature=2, inventory=2)
        self.assertEqual(aggregate_components(values)['Exposure_score'], 10)
        values['inventory'] = None
        partial = aggregate_components(values)
        self.assertEqual(partial['Exposure_score'], 8)
        self.assertEqual(partial['Exposure_observed_score'], 8)
        self.assertEqual(partial['Exposure_available_dimensions'], 4)
        values['human_biomonitoring'] = None
        self.assertEqual(aggregate_components(values)['Exposure_available_dimensions'], 3)
        self.assertEqual(aggregate_components(values)['dimension_scores']['food_contact_and_biomonitoring'], 1)
        self.assertEqual(aggregate_components(values)['Exposure_score'], 7)

    def test_patent_failed_zero_correction_is_not_zero(self):
        gate = {'eligible': False, 'audit_id': 'patent:2', 'exclusion_reasons': ['query_error']}
        self.assertIsNone(select_patent({}, 0, {'pubchem_patent_count': '0'}, gate)['count'])
        result = select_patent({'source': [12]}, 10, {'pubchem_patent_count': '100'}, gate)
        self.assertEqual(result['count'], 12)
        self.assertEqual(result['source'], 'curated_database_extract')
        self.assertEqual(select_patent({'source': [12]}, 30, {}, gate)['count'], 30)
        valid = {'eligible': True, 'audit_id': 'patent:2', 'exclusion_reasons': []}
        self.assertEqual(select_patent({}, 0, {'pubchem_patent_count': '0'}, valid)['count'], 0)
        self.assertIsNone(select_patent({'source': [-10, 'unknown']}, 0, {}, None)['count'])

    def test_reference_error_policy_already_excluded_partial_queries(self):
        record = {'check_status': 'pubchem_patent_ids_found', 'pubchem_patent_count': 100,
                  'existing_patent_count': 0, 'error_message': 'partial CID retrieval'}
        result = reference.external_resolve_patent_selection(0, 0, record)
        self.assertFalse(result['audit']['scoring_eligible'])
        self.assertEqual(result['selected_count'], 0)
        self.assertIsNone(select_patent({}, 0, record, {'eligible': False, 'exclusion_reasons': ['query_error']})['count'])

    def test_source_membership_is_not_model_or_human_detection(self):
        raw = {'inchikey': 'full-key', 'cas_reported': '64-17-5', 'name_resolved': 'Ethanol',
               'db_extract_info': '{}', 'GIC_inventory_listing_count': '', 'GIC_inventory_list_tags': '',
               'GIC_inventory_data_status': 'not_queried', 'source_tables_json': '["fccmigex","fcchumon_s1"]',
               'qsar_smiles': 'changed', 'Persistence_score': 999, 'LRTP_POV_days': 999}
        first = historical_input_view(pd.DataFrame([raw]))
        raw.update(qsar_smiles='different', Persistence_score=-123, LRTP_POV_days=-123)
        second = historical_input_view(pd.DataFrame([raw]))
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first.db_FCCmigex.iloc[0], 1)
        self.assertEqual(first.db_FCChumon_S1.iloc[0], 1)
        self.assertNotIn('qsar_smiles', first)
        inputs = reference.legacy__extract_exposure_inputs(first.iloc[0], 'db_extract_info')
        self.assertEqual(inputs['Exposure_FCChumon_S1_detected'], 0)

    def test_maximum_selector_preserves_ties_and_does_not_sum(self):
        def candidate(value, source='us_epa_cdr', year='2020', record='a'):
            return reference.market__canonical_candidate({'record_id': record, 'source_id': source,
                'quantity_lower_tonnes': '1', 'quantity_upper_tonnes': str(value),
                'reporting_year': year, 'value_status': 'exact', 'evidence_class': 'production_volume',
                'identity_match_status': 'unique_dashboard_match', 'market_presence': 'confirmed_positive_quantity'})
        state = reference.market_CompoundSelectionState('key', '', '')
        state.add(candidate(1000, year='2000'))
        state.add(candidate(900, year='2025'))
        self.assertEqual(state.selected()['selected_tonnes'], '1000')
        state.add(candidate(1000, year='2021', record='b'))
        self.assertEqual(state.selected()['record_id'], 'b')
        state.add(candidate(1000, source='japan_meti_cscl', year='2025', record='z'))
        self.assertEqual(state.selected()['source_id'], 'us_epa_cdr')
        self.assertEqual(state.selected()['selected_tonnes'], '1000')


if __name__ == '__main__':
    unittest.main()
