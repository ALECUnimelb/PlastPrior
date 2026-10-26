"""Independent arithmetic examples and exhaustive component-missingness checks."""
import itertools
import unittest
from copy import deepcopy

from plastprior.exposure import aggregate_components, COMPONENTS
from plastprior.priority import analysis_scores
from test_priority import row_fixture


class ZeroContributionTests(unittest.TestCase):
    def test_user_example_and_input_preservation(self):
        row = row_fixture()
        row.update(Persistence_score='', persistence_available='False',
                   persistence_unavailable_reason='missing', Bioaccumulation_score='1',
                   Mobility_score='1', Toxicity_score='2')
        original = deepcopy(row)
        result = analysis_scores(row)
        self.assertEqual(result['Hazard_score'], 9)
        self.assertEqual(result['Priority_score'], 9)
        self.assertTrue(result['Priority_eligible'])
        self.assertEqual(result['Priority_ineligibility_reasons'], '[]')
        self.assertEqual(row, original)

    def test_every_missingness_pattern(self):
        # Independent literal weights; do not derive expectations from production policy.
        hazard = ['Persistence', 'Bioaccumulation', 'Mobility', 'Toxicity']
        for present in itertools.product([False, True], repeat=10):
            row = row_fixture()
            for i, name in enumerate(hazard):
                row[name + '_score'] = '1' if present[i] else ''
                row[name.lower() + '_available'] = str(present[i])
                row[name.lower() + '_unavailable_reason'] = '' if present[i] else 'missing'
            components = {name: 1 if present[i+4] else None for i, name in enumerate(COMPONENTS)}
            exposure = aggregate_components(components)
            row.update(Exposure_score=exposure['Exposure_score'], Exposure_complete=exposure['Exposure_complete'])
            for name, value in components.items():
                row['Exposure_' + name + '_score'] = value
                row['exposure_' + name + '_available'] = value is not None
                row['exposure_' + name + '_unavailable_reason'] = '' if value is not None else 'missing'
            expected_h = sum(w for w, ok in zip([2, 2, 1, 3], present[:4]) if ok)
            expected_e = sum(present[4:])
            result = analysis_scores(row)
            self.assertEqual(result['Hazard_score'], expected_h)
            self.assertEqual(exposure['Exposure_score'], expected_e)
            self.assertEqual(result['Priority_score'], expected_h + expected_e if any(present) else None)
            self.assertEqual(result['Priority_eligible'], any(present))
            expected_tier = ('No data' if not any(present) else
                             'High priority' if expected_h > 10 and expected_e >= 5 else
                             'Moderate priority' if (6 <= expected_h <= 10 and expected_e >= 5) or (expected_h > 10 and expected_e < 5) else 'Low priority')
            self.assertEqual(result['Priority_tier'], expected_tier)

    def test_joint_contribution_without_false_completeness(self):
        values = dict.fromkeys(COMPONENTS)
        values['food_contact'] = 1
        result = aggregate_components(values)
        self.assertEqual(result['Exposure_score'], 1)
        self.assertEqual(result['dimension_contributions']['food_contact_and_biomonitoring'], 1)
        self.assertFalse(result['dimension_available']['food_contact_and_biomonitoring'])
        self.assertEqual(result['Exposure_available_dimensions'], 0)
        self.assertIsNone(values['human_biomonitoring'])
