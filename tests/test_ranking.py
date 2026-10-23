"""Competition-rank and Top-N boundary invariants for Stage 7B."""
import unittest

import pandas as pd

from plastprior.ranking import eligible_ranking, historical_order


def table(scores):
    return pd.DataFrame([{'inchikey': k, 'Priority_score': v, 'Priority_eligible': str(v != '')} for k, v in scores],
                        columns=['inchikey', 'Priority_score', 'Priority_eligible'])


class RankingTests(unittest.TestCase):
    def test_competition_rank_and_entire_boundary_group(self):
        frame = table([('d', '1'), ('c', '2'), ('a', '3'), ('b', '2')])
        ranks, order, summary = eligible_ranking(frame, 2)
        ranks = ranks.set_index('inchikey')
        self.assertEqual(order, ['a', 'b', 'c', 'd'])
        self.assertEqual(ranks.Priority_rank.tolist(), [1, 2, 2, 4])
        self.assertEqual(ranks.Priority_tie_size.tolist(), [1, 2, 2, 1])
        self.assertEqual(summary['selected_compounds'], 3)
        self.assertEqual(summary['boundary_tie_size'], 2)
        self.assertEqual(summary['cutoff_score'], 2)

    def test_zero_is_ranked_and_missing_is_not_false_membership(self):
        ranks, order, summary = eligible_ranking(table([('zero', '0'), ('missing', '')]), 100)
        by_key = ranks.set_index('inchikey')
        self.assertEqual(order, ['zero'])
        self.assertEqual(by_key.loc['zero', 'Priority_rank'], 1)
        self.assertTrue(by_key.loc['zero', 'Top_n_selected'])
        self.assertTrue(pd.isna(by_key.loc['missing', 'Priority_rank']))
        self.assertTrue(pd.isna(by_key.loc['missing', 'Top_n_selected']))
        self.assertTrue(summary['top_n_exceeds_pool'])

    def test_no_eligible_records(self):
        ranks, order, summary = eligible_ranking(table([('a', ''), ('b', '')]), 1)
        self.assertEqual(order, [])
        self.assertIsNone(summary['cutoff_score'])
        self.assertEqual(summary['selected_compounds'], 0)
        self.assertTrue(ranks.Priority_rank.isna().all())
        self.assertTrue(ranks.Top_n_selected.isna().all())

    def test_all_tied_records_are_included_for_n_one(self):
        ranks, order, summary = eligible_ranking(table([('c', '1'), ('a', '1.0'), ('b', '1.00')]), 1)
        self.assertEqual(order, ['a', 'b', 'c'])
        self.assertTrue(ranks.Priority_rank.eq(1).all())
        self.assertEqual(summary['selected_compounds'], 3)

    def test_comparison_precedes_rounding(self):
        ranks, order, _ = eligible_ranking(table([('a', '1.0000000001'), ('b', '1')]), 1)
        self.assertEqual(order, ['a', 'b'])
        self.assertEqual(ranks.Priority_rank.tolist(), [1, 2])
        self.assertEqual(ranks.Top_n_selected.tolist(), [True, False])

    def test_input_permutation_and_tier_do_not_change_rank(self):
        original = table([('z', '18'), ('a', '12'), ('c', '12'), ('b', '')])
        original['Priority_tier'] = ['Moderate priority', 'High priority', 'Moderate priority', 'Insufficient evidence']
        expected, order, _ = eligible_ranking(original, 2)
        for seed in range(6):
            actual, actual_order, _ = eligible_ranking(original.sample(frac=1, random_state=seed), 2)
            pd.testing.assert_frame_equal(expected, actual)
            self.assertEqual(order, actual_order)
        self.assertEqual(order, ['z', 'a', 'c'])

    def test_invalid_n_duplicate_ids_and_invalid_scores(self):
        for n in [0, -1, True, 1.5, '2']:
            with self.assertRaises(ValueError): eligible_ranking(table([('a', '1')]), n)
        for pairs in [[('a', '1'), ('a', '2')], [('', '1')], [('a', 'NaN')], [('a', '-1')], [('a', '27')]]:
            with self.assertRaises(ValueError): eligible_ranking(table(pairs), 1)

    def test_inconsistent_qualification_is_rejected(self):
        for value, flag in [('1', 'False'), ('', 'True')]:
            with self.assertRaises(ValueError):
                eligible_ranking(pd.DataFrame([{'inchikey': 'a', 'Priority_score': value, 'Priority_eligible': flag}]), 1)

    def test_historical_order_cannot_be_silently_replaced(self):
        with self.assertRaisesRegex(ValueError, 'Historical input order'):
            historical_order(table([('a', '1')]))


if __name__ == '__main__':
    unittest.main()
