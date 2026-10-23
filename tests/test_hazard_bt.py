"""Test B/T model precedence, identity gates, structural rules and curated fallback."""
import json
import unittest
import pandas as pd

from plastprior.hazard_bt import (
    BCF_MODELS, TOXICITY_ENDPOINTS, MODEL_FIELDS, SCORE_COLUMNS,
    _logbcf_to_bioaccum_score, _fish_lc50_to_score_mg_l,
    _score_structural_halogen_rule, _as_binary_activity,
    _pick_structural_halogen_bioaccumulation_from_row, _historical_inputs,
    score_bt, _pathway_decisions,
)


class BTHazardTests(unittest.TestCase):
    def row(self, review=False, smiles='CCO'):
        return {**dict.fromkeys(MODEL_FIELDS, ''), 'inchikey': 'synthetic-full-key', 'qsar_smiles': smiles,
                'db_extract_info': '{}', 'qsar_identity_status': 'review_required' if review else 'exact_key_match',
                'qsar_identity_reason': 'formula_difference' if review else '', 'qsar_evidence_available': not review}

    def score(self, row, **kwargs):
        frame, audits = score_bt(pd.DataFrame([row]), **kwargs)
        return frame.iloc[0], audits

    def bcf(self, row, i, value, adi=1):
        model = BCF_MODELS[i]
        row.update({model['logbcf_col']: value, model['adi_col']: adi, model['assess_col']: 'available'})

    def test_bcf_cutoffs(self):
        for value, expected in [(1.99, 0), (2, 0.5), (2.999, 0.5), (3, 1), (3.699, 1), (3.7, 2)]:
            self.assertEqual(_logbcf_to_bioaccum_score(value), expected)

    def test_bcf_first_usable_model_not_maximum(self):
        row = self.row(); self.bcf(row, 0, 1); self.bcf(row, 1, 4)
        result, _ = self.score(row)
        self.assertEqual(result['Bioaccumulation_score'], 0)
        self.assertEqual(result['Bioaccumulation_score_basis'], 'QSAR_BCF:Arnot-Gobas')

    def test_bcf_adi_boundary_and_fallback_model(self):
        for adi, basis in [(0.49, 'CAESAR'), ('', 'CAESAR'), (0.5, 'Arnot-Gobas')]:
            row = self.row(); self.bcf(row, 0, 2, adi); self.bcf(row, 1, 3)
            result, _ = self.score(row)
            self.assertEqual(result['Bioaccumulation_score_basis'], 'QSAR_BCF:' + basis)

    def test_structural_count_boundaries(self):
        for total, bound, expected in [(0, 0, None), (1, 0, None), (2, 0, 1), (3, 0, 1), (4, 0, 2), (1, 1, 1), (2, 2, 2)]:
            self.assertEqual(_score_structural_halogen_rule(total, bound)[0], expected)

    def test_structural_graphs_and_nonchlorine_halogen(self):
        for smiles, expected in [('CCCl', None), ('ClCCCl', 1), ('Clc1ccccc1', 1), ('Clc1ccc(Br)cc1', 2), ('Fc1ccc(F)cc1', None), ('Ic1ccc(I)cc1', None), ('Clc1ccncc1', None)]:
            result, _ = self.score(self.row(smiles=smiles))
            if expected is None: self.assertTrue(pd.isna(result['Bioaccumulation_score']))
            else: self.assertEqual(result['Bioaccumulation_score'], expected)

    def test_structural_invalid_and_missing_are_not_zero(self):
        for smiles, status in [('', 'missing_smiles'), ('not_a_structure', 'invalid_smiles')]:
            result, _ = self.score(self.row(smiles=smiles))
            self.assertTrue(pd.isna(result['Bioaccumulation_score']))
            self.assertEqual(json.loads(result['Bioaccumulation_evidence'])['structural_halogen_rule']['status'], status)

    def test_bcf_structure_maximum_and_tie(self):
        row = self.row(smiles='Clc1ccccc1'); self.bcf(row, 0, 2)
        result, _ = self.score(row)
        self.assertEqual(result['Bioaccumulation_score_basis'], 'Structural_halogen_rule')
        self.bcf(row, 0, 3)
        result, _ = self.score(row)
        self.assertEqual(result['Bioaccumulation_score_basis'], 'QSAR_BCF:Arnot-Gobas')
        self.assertEqual(len(json.loads(result['Bioaccumulation_evidence'])['independent_selection']['tied_bases']), 2)

    def test_fish_cutoffs(self):
        for value, expected in [(1, 2), (1.0001, 1), (10, 1), (10.001, 0.5), (100, 0.5), (100.001, 0)]:
            self.assertEqual(_fish_lc50_to_score_mg_l(value), expected)

    def test_endpoint_specific_negative_labels(self):
        for endpoint, text in zip(TOXICITY_ENDPOINTS[:5], ['non-mutagenic', 'non-carcinogen', 'non-carcinogen', 'non-toxicant', 'non-active']):
            self.assertEqual(_as_binary_activity(text, endpoint['name']), 0)
        self.assertIsNone(_as_binary_activity('unrecognised', TOXICITY_ENDPOINTS[0]['name']))

    def test_ames_without_adi_is_usable_but_review_is_blocked(self):
        row = self.row(); row[TOXICITY_ENDPOINTS[0]['pred_col']] = 'mutagenic'
        self.assertEqual(self.score(row)[0]['Toxicity_score'], 2)
        row.update(qsar_identity_status='review_required', qsar_evidence_available=False)
        with self.assertRaisesRegex(ValueError, 'leaked'): self.score(row)
        row[TOXICITY_ENDPOINTS[0]['pred_col']] = ''
        result, _ = self.score(row)
        self.assertTrue(pd.isna(result['Toxicity_score']))
        endpoint = json.loads(result['Toxicity_evidence'])['qsar_toxicity']['endpoints'][0]
        self.assertEqual(endpoint['exclude_reason'], 'identity_review_required')

    def test_non_ames_requires_adi(self):
        endpoint = TOXICITY_ENDPOINTS[1]
        for adi, available in [('', False), (0.49, False), (0.5, True)]:
            row = self.row(); row.update({endpoint['pred_col']: 'carcinogen', endpoint['adi_col']: adi})
            result, _ = self.score(row)
            self.assertEqual(pd.notna(result['Toxicity_score']), available)

    def test_toxicity_maximum_and_tie_order(self):
        row = self.row(); row[TOXICITY_ENDPOINTS[0]['pred_col']] = 'non-mutagenic'
        endpoint = TOXICITY_ENDPOINTS[1]; row.update({endpoint['pred_col']: 'carcinogen', endpoint['adi_col']: 1})
        result, _ = self.score(row)
        self.assertEqual(result['Toxicity_score'], 2)
        self.assertEqual(result['Toxicity_score_basis'], 'QSAR_Toxicity:Carcinogenicity_CAESAR')
        row[TOXICITY_ENDPOINTS[0]['pred_col']] = 'mutagenic'
        self.assertEqual(self.score(row)[0]['Toxicity_score_basis'], 'QSAR_Toxicity:Ames_mutagenicity_consensus')

    def test_er_positive_scores_one(self):
        row = self.row(); e = TOXICITY_ENDPOINTS[4]; row.update({e['pred_col']: 'active', e['adi_col']: 1})
        self.assertEqual(self.score(row)[0]['Toxicity_score'], 1)

    def test_independent_zero_precedes_curated(self):
        row = self.row(); self.bcf(row, 0, 1); row[TOXICITY_ENDPOINTS[0]['pred_col']] = 'non-mutagenic'
        row['db_extract_info'] = json.dumps({'hazard': {'B': {'PlastChem': [2]}, 'T': {'PlastChem': [2]}}})
        result, _ = self.score(row)
        self.assertEqual(result[SCORE_COLUMNS].tolist(), [0, 0])

    def test_review_retains_structure_and_curated_and_reason(self):
        row = self.row(True, 'Clc1ccccc1')
        row['db_extract_info'] = json.dumps({'hazard': {'B': {'PlastChem': [2]}, 'T': {'PlastChem': [0.25]}}})
        result, audits = self.score(row)
        self.assertEqual(result[SCORE_COLUMNS].tolist(), [1, 0.25])
        for dim in ['Bioaccumulation', 'Toxicity']:
            self.assertEqual(json.loads(result[dim + '_evidence'])['identity_review']['reason'], 'formula_difference')
            self.assertEqual(audits[dim.lower()][0][dim.lower() + '_from_qsar'], {})

    def test_curated_precedence_and_fraction(self):
        row = self.row(); row['db_extract_info'] = json.dumps({'hazard': {'B': {'A': [2], 'PlastChem': [0.25]}, 'T': {'Z': [2], 'A': [0.5]}}})
        result, _ = self.score(row)
        self.assertEqual(result[SCORE_COLUMNS].tolist(), [0.25, 0.5])

    def test_history_requires_explicit_opt_in(self):
        row = self.row(True); self.bcf(row, 0, 4)
        with self.assertRaisesRegex(ValueError, 'leaked'): self.score(row)
        self.assertEqual(self.score(row, historical=True)[0]['Bioaccumulation_score'], 2)

    def test_unavailable_flag_masks_even_ames(self):
        row = self.row(); row['qsar_evidence_available'] = False
        self.bcf(row, 0, 4); row[TOXICITY_ENDPOINTS[0]['pred_col']] = 'mutagenic'
        result, _ = self.score(row)
        self.assertTrue(result[SCORE_COLUMNS].isna().all())

    def test_annotations_report_structure_and_labels_do_not_score(self):
        row = self.row(); before, _ = self.score(row)
        row.update({'GIC_regulatory_listing_count': 999, 'gic_shared_identifier_tag_expansion': True,
                    'norman_prediction_available': True, 'Basic | Smile_std': 'Clc1ccc(Cl)cc1',
                    'db_extract_info': json.dumps({'regulatory': {'GIC': [2]}, 'analytical_detectability': {'probe': 1}, 'hazard': {'toxicological_labels': {'probe': [2]}}})})
        after, _ = self.score(row)
        pd.testing.assert_series_equal(before, after)

    def test_local_structure_is_used(self):
        row = self.row(smiles='ClCCCl'); row['Basic | Smile_std'] = 'CCO'
        self.assertEqual(self.score(row)[0]['Bioaccumulation_score'], 1)

    def test_join_by_key_and_structure_integrity(self):
        base = pd.DataFrame([self.row(), {**self.row(), 'inchikey': 'other'}])
        historical = base.iloc[::-1].copy(); historical[BCF_MODELS[0]['logbcf_col']] = [4, 2]
        restored = _historical_inputs(base, historical)
        self.assertEqual(restored[BCF_MODELS[0]['logbcf_col']].tolist(), [2, 4])
        historical.loc[historical.index[0], 'qsar_smiles'] = 'CCC'
        with self.assertRaisesRegex(ValueError, 'structural representation'): _historical_inputs(base, historical)

    def test_unvisited_bcf_and_lower_t_endpoint_reasons(self):
        row = self.row(); self.bcf(row, 0, 1); self.bcf(row, 1, 4)
        row[TOXICITY_ENDPOINTS[0]['pred_col']] = 'non-mutagenic'
        endpoint = TOXICITY_ENDPOINTS[1]; row.update({endpoint['pred_col']: 'carcinogen', endpoint['adi_col']: 1})
        result, _ = self.score(row)
        b = {r['candidate']: r['reason'] for r in _pathway_decisions('Bioaccumulation', json.loads(result['Bioaccumulation_evidence']))}
        t = {r['candidate']: r['reason'] for r in _pathway_decisions('Toxicity', json.loads(result['Toxicity_evidence']))}
        self.assertEqual(b['CAESAR'], 'not_evaluated_after_higher_priority_usable_model')
        self.assertEqual(t['Ames_mutagenicity_consensus'], 'lower_endpoint_score')
        self.assertEqual(t['Carcinogenicity_CAESAR'], 'selected_maximum_endpoint')

    def test_invalid_keys_flags_and_nonfinite_values_fail(self):
        row = self.row(); row['inchikey'] = None
        with self.assertRaisesRegex(ValueError, 'unique nonempty'): self.score(row)
        row = self.row(); row['qsar_evidence_available'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'explicit booleans'): self.score(row)
        row = self.row(); self.bcf(row, 0, 'inf')
        with self.assertRaisesRegex(ValueError, 'Nonfinite'): self.score(row)
        with self.assertRaisesRegex(ValueError, 'unique nonempty'): score_bt(pd.DataFrame([self.row(), self.row()]))


if __name__ == '__main__':
    unittest.main()
