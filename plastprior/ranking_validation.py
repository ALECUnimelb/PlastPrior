"""Historical Top-100 parity and independent complete-case ranking checks."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import tempfile

import pandas as pd

from .evidence import _read_csv
from .evidence_specialists import require_prediction_isolation
from .inputs import _file_hash
from .lrtp import _verify_outputs


def compare_ranking(baseline, results, output_dir, upstream_results=None, data_root=None):
    from . import ranking
    from .priority_validation import compare_priority
    from .validation import _verify_hash

    baseline, results, output_dir = (Path(p).resolve() for p in [baseline, results, output_dir])
    upstream = Path(upstream_results).resolve() if upstream_results else results.parent / '7a'
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks, counts = [], [], {}
    def demand(ok, message):
        if not ok:
            raise ValueError(message)
    def number(value):
        return None if value == '' else Decimal(value)
    def derived_ranks(values):
        counts = Counter(values.values())
        return {k: 1 + sum(n for v, n in counts.items() if v > score) for k, score in values.items()}
    try:
        previous = compare_priority(baseline, upstream, output_dir / 'stage7a', data_root=data_root)
        demand(previous['status'] == 'passed', 'Stage 7A or upstream validation failed.')
        manifest = json.loads((results / 'ranking_manifest.json').read_text(encoding='utf-8'))
        _verify_outputs(results, manifest)
        _verify_hash(ranking.POLICY_PATH, manifest['policy_sha256'])
        _verify_hash(Path(ranking.__file__), manifest['implementation_sha256'])
        _verify_hash(upstream / 'priority_manifest.json', manifest['upstream_manifest_sha256'])
        n = manifest['top_n']
        demand(type(n) is int and n > 0, 'Invalid Top-N configuration.')
        prior = _read_csv(upstream / 'compound_priority_assessment.csv').set_index('inchikey')
        all_records = _read_csv(results / 'compound_rankings.csv')
        keys = all_records['inchikey'].tolist()
        demand(keys == sorted(prior.index) and len(set(keys)) == len(prior), 'Ranking universe or canonical order changed.')
        indexed = all_records.set_index('inchikey')
        for c in prior:
            demand(indexed[c].tolist() == prior.loc[keys, c].tolist(), 'Upstream field changed: ' + c)
        require_prediction_isolation(all_records)
        eligible = prior['Priority_eligible'].eq('True')
        scores = {k: Decimal(v) for k, v in prior.loc[eligible, 'Priority_score'].items()}
        expected_ranks = derived_ranks(scores)
        groups = Counter(scores.values())
        order = sorted(scores, key=lambda k: (-scores[k], k))
        cutoff = scores[order[min(n, len(order)) - 1]] if order else None
        selected = [k for k in order if scores[k] >= cutoff]
        for row in all_records.to_dict('records'):
            key = row['inchikey']
            if key in scores:
                demand(row['Ranking_eligible'] == 'True' and int(row['Priority_rank']) == expected_ranks[key], 'Competition rank differs: ' + key)
                demand(int(row['Priority_tie_size']) == groups[scores[key]], 'Tie group size differs.')
                demand(row['Top_n_selected'] == str(key in selected), 'Top-N boundary membership differs.')
            else:
                demand(row['Ranking_eligible'] == 'False' and all(row[c] == '' for c in ['Priority_rank', 'Priority_tie_size', 'Top_n_selected']), 'Ineligible record acquired rank or valid membership.')
            demand(row['Ranking_exclusion_reasons'] == row['Priority_ineligibility_reasons'], 'Missingness reason changed.')
        for name, wanted in [('eligible_priority_ranking', order), ('top_priority_including_ties', selected),
                             ('unranked_review', sorted(set(keys) - set(order)))]:
            table = _read_csv(results / (name + '.csv'))
            demand(table['inchikey'].tolist() == wanted, 'Export order or membership differs: ' + name)
            for c in table.columns.drop('inchikey'):
                demand(table[c].tolist() == indexed.loc[wanted, c].tolist(), 'Export fields differ: ' + name + ':' + c)
        review = all_records['qsar_identity_status'].eq('review_required')
        demand(int(review.sum()) == 15, 'Identity-review cohort changed.')
        # Source-level exclusions do not exclude independently scoreable compounds.
        _verify_hash(results / 'identity_review_source_links.jsonl', _file_hash(upstream / 'identity_review_source_links.jsonl'))
        checkpoint_path = baseline / '07. Prioritization' / 'checkpoint.json'
        _verify_hash(checkpoint_path, ranking.POLICY['historical']['checkpoint_sha256'])
        checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        artifacts = {a['artifact_id']: a for a in checkpoint['artifacts']}
        full_path = baseline / artifacts['compound_priority_table_csv']['path']
        top_path = baseline / artifacts['top_priority_chemicals_csv']['path']
        _verify_hash(full_path, artifacts['compound_priority_table_csv']['sha256'])
        _verify_hash(top_path, artifacts['top_priority_chemicals_csv']['sha256'])
        _verify_hash(top_path, ranking.POLICY['historical']['top100_sha256'])
        history = _read_csv(upstream / 'priority_historical.csv')
        science = [c for c in history if c not in ['inchikey', 'result_role']]
        old_full = pd.read_csv(full_path, usecols=['Inchikey_std'] + science, dtype=str, keep_default_na=False, encoding='utf-8').rename(columns={'Inchikey_std': 'inchikey'})
        demand(old_full['inchikey'].tolist() == history['inchikey'].tolist(), 'Frozen historical input order differs.')
        old_full['_sort'] = pd.to_numeric(old_full['Priority_score'])
        legacy = old_full.sort_values('_sort', ascending=False, kind='quicksort', na_position='last').drop(columns='_sort').reset_index(drop=True)
        old_top = _read_csv(top_path).rename(columns={'Inchikey_std': 'inchikey'})
        historical = _read_csv(results / 'historical_priority_order.csv')
        historical_top = _read_csv(results / 'historical_top100.csv')
        demand(historical['inchikey'].tolist() == legacy['inchikey'].tolist(), 'Historical quicksort order differs.')
        demand(historical_top['inchikey'].tolist() == old_top['inchikey'].tolist(), 'Frozen Top-100 order or membership differs.')
        for expected, actual, columns in [(legacy, historical, science), (old_top, historical_top, [c for c in science if c in old_top])]:
            for c in columns:
                numeric = c.endswith('_score')
                for key, a, b in zip(actual['inchikey'], expected[c], actual[c]):
                    if (number(a) != number(b)) if numeric else (a != b):
                        differences.append({'scope': 'historical_field', 'inchikey': key, 'field': c, 'expected': a, 'actual': b})
        omitted = [c for c in old_top if c not in historical_top]
        checks.append({'scope': 'historical_order_and_top100', 'compounds': len(history), 'top100_rows': len(old_top),
                       'full_table_fields': len(science), 'top100_fields': len([c for c in science if c in old_top]),
                       'legacy_top100_columns_outside_reconstruction_scope': omitted})
        historical_scores = {k: Decimal(v) for k, v in zip(history['inchikey'], history['Priority_score'])}
        r0 = derived_ranks(historical_scores)
        r1 = derived_ranks({k: historical_scores[k] for k in order})
        old_members = set(legacy.head(n)['inchikey'])
        old_positions = {key: i + 1 for i, key in enumerate(legacy['inchikey'])}
        display_positions = {key: i + 1 for i, key in enumerate(order)}
        old100 = set(old_top['inchikey'])
        old_cut = Decimal(legacy.iloc[min(n, len(legacy)) - 1]['Priority_score'])
        old_inclusive = {k for k, v in historical_scores.items() if v >= old_cut}
        demand([int(v) for v in historical['Historical_sort_position']] == list(range(1, len(history) + 1)), 'Legacy ordinal positions differ.')
        old_groups = Counter(historical_scores.values())
        for row in historical.to_dict('records'):
            key = row['inchikey']
            demand(int(row['Historical_derived_score_rank']) == r0[key] and int(row['Historical_tie_size']) == old_groups[historical_scores[key]], 'Historical derived rank or tie size differs.')
        audit = _read_csv(results / 'ranking_changes.csv')
        demand(audit['inchikey'].tolist() == keys, 'Change audit coverage differs.')
        for row in audit.to_dict('records'):
            key = row['inchikey']
            demand(int(row['requested_n']) == n and int(row['historical_derived_rank']) == r0[key], 'Audit scope or historical rank differs.')
            demand(int(row['historical_sort_position']) == old_positions[key], 'Historical display position differs.')
            demand(row['historical_top100_member'] == str(key in old100) and row['historical_strict_top_n_member'] == str(key in old_members), 'Historical membership audit differs.')
            demand(number(row['historical_score']) == historical_scores[key], 'Historical audit score differs.')
            reasons = []
            if key in scores:
                demand(number(row['analysis_score']) == scores[key] and row['analysis_top_n_member'] == str(key in selected), 'Analysis membership or score audit differs.')
                expected = {'historical_rank_in_current_eligible_pool': r1[key], 'analysis_rank': expected_ranks[key],
                            'analysis_display_position': display_positions[key],
                            'eligibility_pool_rank_shift': r1[key] - r0[key], 'score_update_rank_shift': expected_ranks[key] - r1[key]}
                demand(all(int(row[c]) == value for c, value in expected.items()), 'Rank-change decomposition differs.')
                if r1[key] != r0[key]: reasons.append('ranking_pool_changed_by_eligibility')
                if scores[key] != historical_scores[key]: reasons.append('own_priority_score_changed_upstream')
                if expected_ranks[key] != r1[key]: reasons.append('relative_order_changed_by_score_updates_within_eligible_pool')
                if groups[scores[key]] > 1: reasons.append('tied_group_displayed_by_identifier_without_breaking_rank_tie')
            else:
                demand(all(row[c] == '' for c in ['analysis_score', 'analysis_top_n_member', 'analysis_rank', 'analysis_display_position', 'historical_rank_in_current_eligible_pool', 'eligibility_pool_rank_shift', 'score_update_rank_shift']), 'Ineligible audit acquired numeric rank or membership.')
                reasons.append('ineligible_no_available_evidence')
            if key in old_inclusive and key not in old_members: reasons.append('historical_strict_top_n_truncated_boundary_tie')
            if (key in old_members) != (key in selected): reasons.append('top_n_membership_changed')
            if not reasons: reasons.append('unchanged_competition_rank_and_membership')
            demand(json.loads(row['change_reasons']) == reasons, 'Unsupported ranking change explanation.')
            demand(row['ineligibility_reasons'] == prior.loc[key, 'Priority_ineligibility_reasons'], 'Audit exclusion reasons differ.')
            demand(row['source_join_key'] == key and row['source_decision_file'] == 'priority_decisions.jsonl' and row['upstream_manifest_sha256'] == manifest['upstream_manifest_sha256'], 'Source-decision reference differs.')
        checks.append({'scope': 'independent_rank_boundary_exclusion_and_change_accounting', 'eligible': len(order), 'selected': len(selected), 'unranked': len(keys) - len(order)})
        shuffled = prior.reset_index().sample(frac=1, random_state=173)
        shuffled_ranks, shuffled_order, shuffled_summary = ranking.eligible_ranking(shuffled, n)
        reference_ranks, _, _ = ranking.eligible_ranking(prior.reset_index(), n)
        pd.testing.assert_frame_equal(shuffled_ranks, reference_ranks)
        demand(shuffled_order == order, 'Input permutation changed the analysis display order.')
        summary = json.loads((results / 'ranking_summary.json').read_text(encoding='utf-8'))
        demand(summary == manifest['counts'], 'Summary and manifest disagree.')
        for c, value in shuffled_summary.items(): demand(summary[c] == value, 'Top-N summary differs: ' + c)
        demand(summary['top_n_membership_entered'] == len(set(selected) - old_members) and summary['top_n_membership_left'] == len(old_members - set(selected)), 'Membership-change counts differ.')
        replay = ranking.integrate_ranking(upstream, n)
        with tempfile.TemporaryDirectory(prefix='PlastPrior ranking validation ') as folder:
            replay.write_reports(folder)
            demand(replay.manifest == manifest, 'Deterministic reconstruction differs.')
        checks.append({'scope': 'permutation_invariance_and_deterministic_reconstruction', 'files': len(manifest['output_sha256']) + 1})
        counts = manifest['counts']
    except (ValueError, KeyError, OSError, TypeError, StopIteration, ArithmeticError, AssertionError) as exc:
        differences.append({'scope': 'ranking_validation', 'detail': str(exc)})
    report = {'stage': '7B', 'status': 'passed' if not differences else 'failed', 'difference_count': len(differences),
              'counts': counts, 'checks': checks, 'comparison': 'Frozen historical order and Top-100 migrated fields; independent competition ranks, inclusive boundaries, exclusion reasons and change decomposition.'}
    pd.DataFrame(differences).to_csv(output_dir / 'ranking_differences.csv', index=False, encoding='utf-8', lineterminator='\n')
    (output_dir / 'ranking_validation_summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
