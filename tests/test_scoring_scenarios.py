"""Scenario invariants, approved label matrix and explicitly synthetic boundary tests."""
from copy import deepcopy
from decimal import Decimal
import unittest

from plastprior.scoring_scenarios import (
    COMPONENT_MAXIMA, EXPOSURE_WEIGHTS, HAZARD_WEIGHTS,
    domain_label, priority_level, weighted_domain,
)


class ScenarioTests(unittest.TestCase):
    def test_all_sixteen_label_combinations(self):
        labels = ['vH', 'H', 'M', 'L']
        expected = [[1, 1, 2, 2], [1, 2, 3, 3], [2, 3, 4, 4], [2, 3, 4, 4]]
        for i, hazard in enumerate(labels):
            for j, exposure in enumerate(labels):
                self.assertEqual(priority_level(hazard, exposure), expected[i][j])
        self.assertIsNone(priority_level(None, 'vH'))
        with self.assertRaises(ValueError):
            priority_level('unknown', 'L')

    def test_approved_default_maxima_and_unchanged_source(self):
        record = dict(COMPONENT_MAXIMA)
        before = deepcopy(record)
        for domain, weights in [('hazard', HAZARD_WEIGHTS), ('exposure', EXPOSURE_WEIGHTS)]:
            result = weighted_domain(record, weights, domain, normalize_to=None)
            self.assertEqual(result['score'], 16)
            self.assertEqual(result['maximum'], 16)
        self.assertEqual(record, before)

    def test_missing_is_zero_only_in_sum_and_not_renormalized(self):
        record = {field: None for field in COMPONENT_MAXIMA}
        record['Exposure_inventory_score'] = 2
        result = weighted_domain(record, EXPOSURE_WEIGHTS, 'exposure', normalize_to=16)
        self.assertEqual(result['score'], 6)
        self.assertTrue(result['has_active_evidence'])
        self.assertFalse(result['complete'])
        self.assertIn('Exposure_patent_score', result['missing_fields'])
        self.assertIsNone(record['Exposure_patent_score'])

    def test_repeated_calls_do_not_compound_weights(self):
        record = {field: 0 for field in COMPONENT_MAXIMA}
        record['Exposure_inventory_score'] = 1
        for _ in range(3):
            self.assertEqual(weighted_domain(record, EXPOSURE_WEIGHTS, 'exposure', normalize_to=None)['score'], 3)

    def test_normalization_scales_by_theoretical_not_observed_maximum(self):
        record = dict(COMPONENT_MAXIMA)
        weights = {field: value * 2 for field, value in EXPOSURE_WEIGHTS.items()}
        result = weighted_domain(record, weights, 'exposure', normalize_to=16)
        self.assertEqual(result['raw_score'], 32)
        self.assertEqual(result['score'], 16)
        self.assertEqual(sum(result['contributions'].values()), 16)

    def test_synthetic_cutpoints_and_both_boundary_conventions(self):
        # These are test inputs, NOT approved scientific cutpoints.
        for cut, lower, upper in [(3, 'L', 'M'), (7, 'M', 'H'), (11, 'H', 'vH')]:
            self.assertEqual(domain_label(cut, [3, 7, 11], upper_inclusive=True), upper)
            self.assertEqual(domain_label(cut, [3, 7, 11], upper_inclusive=False), lower)
        with self.assertRaises(ValueError):
            domain_label(5, None, upper_inclusive=True)

    def test_invalid_components_and_weights_rejected(self):
        for invalid in [-1, float('nan'), float('inf'), True, 'bad']:
            record = dict(COMPONENT_MAXIMA)
            record['Exposure_inventory_score'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                weighted_domain(record, EXPOSURE_WEIGHTS, 'exposure', normalize_to=None)
        with self.assertRaises(ValueError):
            weighted_domain({}, EXPOSURE_WEIGHTS, 'exposure', normalize_to=None)
        with self.assertRaises(ValueError):
            weighted_domain(COMPONENT_MAXIMA, {field: 0 for field in EXPOSURE_WEIGHTS}, 'exposure', normalize_to=16)

    def test_zero_weight_evidence_does_not_create_active_domain_evidence(self):
        record = {field: None for field in COMPONENT_MAXIMA}
        record['Exposure_inventory_score'] = 2
        weights = {**EXPOSURE_WEIGHTS, 'Exposure_inventory_score': 0}
        result = weighted_domain(record, weights, 'exposure', normalize_to=None)
        self.assertEqual(result['score'], Decimal(0))
        self.assertFalse(result['has_active_evidence'])

class RoundedScenarioTests(unittest.TestCase):
    def test_domain_rounding_before_total_and_labels(self):
        from plastprior.scoring_scenarios import default_policy, score_population
        row = {field: 0 for field in COMPONENT_MAXIMA}
        row.update(inchikey='A', Persistence_score='0.25', Exposure_patent_score='0.25')
        result = score_population([row], default_policy())[0]
        self.assertEqual((result['Hazard_score'], result['Exposure_score'], result['Priority_score']), (1, 1, 2))
        self.assertEqual(Decimal(result['Hazard_score_raw']), Decimal('.5'))
        row.update(Persistence_score=0, Toxicity_score=2, Mobility_score='1.5')
        result = score_population([row], default_policy())[0]
        self.assertEqual((result['Hazard_score'], result['Hazard_label']), (8, 'H'))

    def test_ranking_uses_rounded_total_and_includes_boundary_ties(self):
        from plastprior.scoring_scenarios import default_policy, score_population
        base = {field: 0 for field in COMPONENT_MAXIMA}
        rows = [{**base, 'inchikey': 'B', 'Persistence_score': '.25'},
                {**base, 'inchikey': 'A', 'Persistence_score': '.5'},
                {**base, 'inchikey': 'C', 'Persistence_score': '0'}]
        result = score_population(rows, {**default_policy(), 'top_n': 1})
        self.assertEqual([r['inchikey'] for r in result], ['A', 'B', 'C'])
        self.assertEqual([r['Priority_rank'] for r in result], [1, 1, 3])
        self.assertEqual([r['Top_n_selected'] for r in result], [True, True, False])

    def test_no_evidence_remains_unranked(self):
        from plastprior.scoring_scenarios import default_policy, score_population
        row = {field: None for field in COMPONENT_MAXIMA}
        result = score_population([{**row, 'inchikey': 'A'}], default_policy())[0]
        self.assertIsNone(result['Priority_level'])
        self.assertIsNone(result['Priority_rank'])
        self.assertEqual(result['Hazard_label'], '')
