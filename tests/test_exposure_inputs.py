"""Eligibility boundaries for exposure intake; no research data required."""
import tempfile
from pathlib import Path
import unittest

from plastprior.exposure_inputs import (
    external_eligibility, gic_tag_eligibility, market_eligibility, number,
    relative_file, csv_rows, integrate_exposure_evidence,
)


class ExposureEligibilityTests(unittest.TestCase):
    def test_default_data_root_and_upstream_output_protection(self):
        result = integrate_exposure_evidence(Path('results') / 'stage5' / '5b')
        self.assertTrue(result.data_root.is_absolute())
        self.assertEqual(result.data_root.name, 'data')
        with self.assertRaisesRegex(ValueError, 'must not overwrite'):
            result.write_reports(result.bt_directory)

    def market(self, **changes):
        record = {'source_id': 'official', 'identity_match_status': 'unique_dashboard_match',
                  'market_presence': 'confirmed_confidential_quantity', 'quantity_lower_tonnes': '',
                  'quantity_upper_tonnes': '', 'quantity_unit': 'metric_tonne/year'}
        record.update(changes)
        return market_eligibility(record, True, {'official': {'selection_eligibility': 'eligible_compound_numeric'}})

    def test_qualitative_evidence_does_not_require_numeric_quantity(self):
        result = self.market()
        self.assertTrue(result['qualitative_eligible'])
        self.assertFalse(result['numeric_eligible'])
        self.assertEqual(result['numeric_exclusion_reasons'], ['no_usable_numeric_quantity'])

    def test_ambiguous_identity_cannot_supply_qualitative_positive(self):
        result = self.market(identity_match_status='ambiguous_dashboard_cas_mapping',
                             market_presence='confirmed_positive_quantity', quantity_upper_tonnes='200')
        self.assertFalse(result['qualitative_eligible'])
        self.assertFalse(result['numeric_eligible'])
        self.assertIn('unaccepted_identity_mapping', result['qualitative_exclusion_reasons'])

    def test_unknown_source_is_not_permissive(self):
        self.assertFalse(self.market(source_id='unregistered')['qualitative_eligible'])

    def test_unknown_presence_is_not_zero(self):
        self.assertFalse(self.market(market_presence='unknown')['qualitative_eligible'])
        self.assertTrue(self.market(market_presence='confirmed_zero_quantity')['qualitative_eligible'])
        self.assertTrue(self.market(quantity_lower_tonnes='0')['numeric_eligible'])

    def test_invalid_bounds_and_units(self):
        for changes in [{'quantity_lower_tonnes': '-1'}, {'quantity_upper_tonnes': 'NaN'},
                        {'quantity_lower_tonnes': '9', 'quantity_upper_tonnes': '2'},
                        {'quantity_lower_tonnes': '2', 'quantity_unit': 'kg'}]:
            self.assertFalse(self.market(**changes)['numeric_eligible'])
        self.assertTrue(self.market(quantity_upper_tonnes='2', quantity_unit='metric_tonne')['numeric_eligible'])
        self.assertIsNone(number(True))
        self.assertIsNone(number('Infinity'))

    def test_gic_union_of_direct_support_not_blanket_sid_rejection(self):
        resolution = {'match_method': 'cid_bridge', 'matched_sids': [1, 2]}
        sources = {1: {'local_list_tags': ['A']}, 2: {'local_list_tags': ['B']}}
        listing = {'list_tag': 'A', 'regulatory_action_class': 'inventory_registration_or_use_only', 'is_auxiliary': False}
        result = gic_tag_eligibility(resolution, listing, sources)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['direct_support_sids'], [1])
        listing['list_tag'] = 'C'
        self.assertFalse(gic_tag_eligibility(resolution, listing, sources)['eligible'])
        resolution['match_method'] = 'chemical_name'
        listing['list_tag'] = 'A'
        self.assertIn('name_only_association_requires_review', gic_tag_eligibility(resolution, listing, sources)['exclusion_reasons'])

    def test_regulatory_and_auxiliary_tags_do_not_count_as_inventory(self):
        resolution = {'match_method': 'cid_bridge', 'matched_sids': [1]}
        for listing in [{'list_tag': 'A', 'is_auxiliary': True, 'regulatory_action_class': 'inventory_registration_or_use_only'},
                        {'list_tag': 'A', 'is_auxiliary': False, 'regulatory_action_class': 'prohibited_or_banned'}]:
            self.assertFalse(gic_tag_eligibility(resolution, listing, {1: {'local_list_tags': ['A']}})['eligible'])

    def test_patent_zero_correction_requires_completed_consistent_query(self):
        row = {'check_status': 'pubchem_no_patent_ids', 'pubchem_patent_count': '0',
               'existing_patent_count': '0', 'error_message': ''}
        self.assertTrue(external_eligibility('patent', row, True)['eligible'])
        self.assertFalse(external_eligibility('patent', row, True, lite_positive=True)['eligible'])
        self.assertFalse(external_eligibility('patent', row, True, curated_positive=True)['eligible'])
        for changes in [{'check_status': 'no_pubchem_cid'}, {'pubchem_patent_count': ''},
                        {'pubchem_patent_count': '3'}, {'error_message': 'timeout'}, {'existing_patent_count': 'unknown'}]:
            self.assertFalse(external_eligibility('patent', {**row, **changes}, True)['eligible'])

    def test_pubmed_unknown_failed_outside_and_zero_are_distinct(self):
        row = {'status': 'ok', 'pubmed_title_abstract_count': '0', 'error_message': ''}
        self.assertTrue(external_eligibility('pubmed', row, True)['eligible'])
        self.assertFalse(external_eligibility('pubmed', row, False)['eligible'])
        for changes in [{'status': 'no_candidate_term'}, {'pubmed_title_abstract_count': ''},
                        {'pubmed_title_abstract_count': '-1'}, {'pubmed_title_abstract_count': '0.5'}, {'error_message': 'error'}]:
            self.assertFalse(external_eligibility('pubmed', {**row, **changes}, True)['eligible'])

    def test_path_traversal_and_malformed_rows_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(relative_file(root, 'source/data.csv'), root.resolve() / 'source' / 'data.csv')
            for value in ['../outside', '/absolute', 'C:\\absolute', 'a/../../outside']:
                with self.assertRaises(ValueError):
                    relative_file(root, value)
            path = root / 'bad.csv'
            path.write_text('a,b\n1\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                list(csv_rows(path))


if __name__ == '__main__':
    unittest.main()
