"""Independent frozen-run comparison and eligibility checks for Stage 7A."""
from decimal import Decimal
import json
from pathlib import Path
import tempfile

import pandas as pd

from .evidence import _read_csv
from .evidence_specialists import require_prediction_isolation
from .inputs import _file_hash
from .lrtp import _verify_outputs


def compare_priority(baseline, results, output_dir, upstream_results=None, data_root=None):
    from . import priority
    from .exposure_validation import compare_exposure_scores
    from .validation import _verify_hash

    baseline, results, output_dir = (Path(p).resolve() for p in [baseline, results, output_dir])
    upstream = Path(upstream_results).resolve() if upstream_results else results.parent.parent / 'stage6' / '6b'
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks, counts = [], [], {}
    def demand(ok, message):
        if not ok:
            raise ValueError(message)
    def number(value):
        if value is None or value == '':
            return None
        result = Decimal(str(value))
        demand(result.is_finite(), 'Non-finite result.')
        return result
    def equal(a, b, numeric):
        return number(a) == number(b) if numeric else a == b
    try:
        previous = compare_exposure_scores(baseline, upstream, output_dir / 'stage6b', data_root=data_root)
        demand(previous['status'] == 'passed', 'Stage 6B and upstream validation failed.')
        manifest = json.loads((results / 'priority_manifest.json').read_text(encoding='utf-8'))
        _verify_outputs(results, manifest)
        _verify_hash(priority.POLICY_PATH, manifest['policy_sha256'])
        _verify_hash(Path(priority.__file__), manifest['implementation_sha256'])
        root = upstream.parent.parent
        paths = {'exposure': upstream / 'exposure_scoring_manifest.json',
                 'pm': root / 'stage5' / 'hazard_manifest.json', 'bt': root / 'stage5' / '5b' / 'bt_manifest.json'}
        for k, path in paths.items():
            _verify_hash(path, manifest['upstream_manifests_sha256'][k])
        demand(manifest['ranking_computed'] is False, 'Ranking is outside Stage 7A.')
        run_path = baseline / 'run_manifest.json'
        _verify_hash(run_path, priority.POLICY['baseline']['run_manifest_sha256'])
        run = json.loads(run_path.read_text(encoding='utf-8'))
        checkpoint_path = baseline / run['stages']['7']['checkpoint']
        _verify_hash(checkpoint_path, run['stages']['7']['checkpoint_sha256'])
        _verify_hash(checkpoint_path, priority.POLICY['baseline']['checkpoint_sha256'])
        checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        artifact = next(a for a in checkpoint['artifacts'] if a['artifact_id'] == 'compound_priority_table_csv')
        frozen_path = baseline / artifact['path']
        _verify_hash(frozen_path, artifact['sha256'])
        fields = ['Hazard_score', 'Exposure_score', 'Priority_score', 'Hazard_data_status',
                  'Exposure_data_status', 'Priority_data_status', 'Priority_tier']
        hazard = ['Persistence_score', 'Mobility_score', 'Bioaccumulation_score', 'Toxicity_score']
        exposure = ['food_contact', 'human_biomonitoring', 'inventory', 'production', 'patent', 'literature']
        components = hazard + ['Exposure_' + c + '_score' for c in exposure]
        old = pd.read_csv(frozen_path, usecols=['Inchikey_std'] + fields + components,
                          dtype=str, keep_default_na=False, encoding='utf-8').rename(columns={'Inchikey_std': 'inchikey'})
        history, analysis, prior = [_read_csv(p) for p in [results / 'priority_historical.csv',
                                                        results / 'compound_priority_assessment.csv',
                                                        upstream / 'compound_exposure_scores.csv']]
        keys = prior['inchikey'].tolist()
        for name, frame in [('historical', history), ('analysis', analysis), ('frozen', old)]:
            demand(not frame['inchikey'].duplicated().any() and set(frame['inchikey']) == set(keys), 'Compound universe differs: ' + name)
        demand(history['inchikey'].tolist() == keys == analysis['inchikey'].tolist(), 'Output order changed.')
        demand(history['result_role'].eq('historical_reproduction_only').all(), 'Historical role is ambiguous.')
        demand(analysis['priority_result_role'].eq('analysis_after_eligibility_audit').all(), 'Analysis role is ambiguous.')
        demand(not any('rank' in c.lower() for c in analysis.columns), 'Ranking field found in Stage 7A.')
        old = old.set_index('inchikey').loc[keys]
        history_index = history.set_index('inchikey')
        for c in fields + components:
            numeric = c.endswith('_score')
            for key, expected, actual in zip(keys, old[c], history[c]):
                if not equal(expected, actual, numeric):
                    differences.append({'scope': 'historical_field', 'inchikey': key, 'field': c,
                                        'expected': expected, 'actual': actual})
        checks.append({'scope': 'frozen_historical_field_comparison', 'compounds': len(keys),
                       'final_fields': len(fields), 'input_component_fields': len(components)})
        for c in prior.columns:
            demand(prior[c].tolist() == analysis[c].tolist(), 'Upstream field changed: ' + c)
        require_prediction_isolation(analysis)
        review = analysis['qsar_identity_status'].eq('review_required')
        demand(int(review.sum()) == 15 and analysis.loc[review, 'Priority_eligible'].eq('False').all(), 'Frozen identity cohort became eligible.')
        demand(_file_hash(upstream / 'identity_review_source_links.jsonl') == _file_hash(results / 'identity_review_source_links.jsonl'), 'Identity source links changed.')
        decision_rows = [json.loads(line) for line in (results / 'priority_decisions.jsonl').read_text(encoding='utf-8').splitlines()]
        demand([r['inchikey'] for r in decision_rows] == keys, 'Decision audit coverage or order changed.')
        expected_changes = {}
        for row, audit in zip(analysis.to_dict('records'), decision_rows):
            key = row['inchikey']
            h = [number(row[c]) for c in hazard]
            e = [number(row['Exposure_' + c + '_score']) for c in exposure]
            hc, ec = all(v is not None for v in h), all(v is not None for v in e)
            eligible = hc and ec
            observed = sum(v * w for v, w in zip(h, [2, 1, 2, 3]) if v is not None)
            total_e = sum(v for v in e if v is not None)
            expected_h, expected_total = observed if hc else None, observed + total_e if eligible else None
            expected_tier = ('Insufficient evidence' if not eligible else
                             'High priority' if expected_total >= 12 and observed >= 4 and total_e >= 4 else
                             'Moderate priority' if expected_total >= 6 and observed >= 2 and total_e >= 2 else 'Low priority')
            expected = {'Hazard_score': expected_h, 'Hazard_observed_score': observed,
                        'Hazard_available_dimensions': sum(v is not None for v in h),
                        'Priority_score': expected_total}
            for c, value in expected.items():
                demand(number(row[c]) == value, 'Independent aggregate or missingness differs: ' + key + ':' + c)
            demand(row['Hazard_complete'] == str(hc) and row['Priority_eligible'] == str(eligible), 'Completeness differs: ' + key)
            demand(row['Priority_tier'] == expected_tier, 'Independent tier differs: ' + key)
            demand(row['Priority_data_status'] == ('Complete' if eligible else 'Insufficient evidence'), 'Priority status differs.')
            for domain, values in [('Hazard', h), ('Exposure', e)]:
                available = sum(v is not None for v in values)
                expected_status = 'Complete' if available == len(values) else 'Partial' if available else 'Unavailable'
                demand(row[domain + '_data_status'] == expected_status, 'Domain status differs.')
            missing_h = [c.removesuffix('_score') for c, v in zip(hazard, h) if v is None]
            demand(json.loads(row['Hazard_missing_dimensions']) == missing_h, 'Missing hazard dimension list differs.')
            reasons = [{'domain': 'hazard', 'dimension': c, 'reason': row[c.lower() + '_unavailable_reason']} for c in missing_h]
            reasons += [{'domain': 'exposure', 'dimension': c, 'reason': row['exposure_' + c + '_unavailable_reason']}
                        for c, v in zip(exposure, e) if v is None]
            demand(json.loads(row['Priority_ineligibility_reasons']) == reasons, 'Missingness reasons changed.')
            demand(all(r['reason'] for r in reasons), 'Missing exclusion explanation.')
            demand(audit['upstream_manifests_sha256'] == manifest['upstream_manifests_sha256'], 'Decision input hashes differ.')
            demand(audit['source_join_key'] == key, 'Source lineage key differs.')
            demand(audit['source_decision_files'] == {'pm': 'pm_decisions.jsonl', 'bt': 'bt_decisions.jsonl', 'exposure': 'exposure_analysis_decisions.jsonl'}, 'Source decision references differ.')
            demand(audit['gic_context'] == {c: row[c] for c in row if c.startswith(('gic_', 'GIC_'))}, 'GIC audit context changed.')
            for c, value in audit['analysis'].items():
                demand(equal(value, row[c], c.endswith('_score') or isinstance(value, (int, float))) if not isinstance(value, bool) else str(value) == row[c], 'Decision disagrees with analysis: ' + c)
            hist = history_index.loc[key]
            for c, weight in zip(hazard, [2, 1, 2, 3]):
                component = audit['hazard_components'][c]
                demand(number(component['historical_score']) == number(hist[c]) and
                       number(component['analysis_score']) == number(row[c]) and component['weight'] == weight and
                       component['unavailable_reason'] == row[c.removesuffix('_score').lower() + '_unavailable_reason'],
                       'Hazard component lineage differs.')
            for c in exposure:
                component = audit['exposure_components'][c]
                demand(number(component['historical_score']) == number(hist['Exposure_' + c + '_score']) and
                       number(component['analysis_score']) == number(row['Exposure_' + c + '_score']) and
                       component['unavailable_reason'] == row['exposure_' + c + '_unavailable_reason'],
                       'Exposure component lineage differs.')
            for c in fields:
                demand(equal(audit['historical'][c], hist[c], c.endswith('_score')), 'Historical decision disagrees with output.')
                if not equal(hist[c], row[c], c.endswith('_score')):
                    expected_changes[(key, c)] = (hist[c], row[c])
        changes = _read_csv(results / 'priority_changes.csv')
        demand(not changes.duplicated(['inchikey', 'field']).any(), 'Duplicate change records.')
        demand(set(zip(changes['inchikey'], changes['field'])) == set(expected_changes), 'Change coverage is incomplete or spurious.')
        by_key = analysis.set_index('inchikey')
        for record in changes.to_dict('records'):
            key, field = record['inchikey'], record['field']
            before, after = expected_changes[(key, field)]
            demand(equal(json.loads(record['historical_value']), before, field.endswith('_score')), 'Change before-value differs.')
            demand(equal(json.loads(record['analysis_value']), after, field.endswith('_score')), 'Change after-value differs.')
            demand(json.loads(record['missing_reasons']) == json.loads(by_key.loc[key, 'Priority_ineligibility_reasons']), 'Change exclusion reasons differ.')
            h_old = history_index.loc[key]
            a_row = by_key.loc[key]
            expected_reasons = []
            if field.endswith('data_status'):
                expected_reasons.append('availability_status_distinguishes_complete_partial_and_unavailable')
            if not field.startswith('Exposure') and any(number(h_old[c]) != number(a_row[c]) for c in hazard):
                expected_reasons.append('upstream_hazard_identity_isolation')
            if not field.startswith('Hazard') and any(number(h_old[c]) != number(a_row[c]) for c in components[4:]):
                expected_reasons.append('upstream_exposure_eligibility_audit')
            incomplete = (a_row['Hazard_complete'] == 'False' if field.startswith('Hazard') else
                          a_row['Exposure_complete'] == 'False' if field.startswith('Exposure') else
                          a_row['Priority_eligible'] == 'False')
            if incomplete:
                expected_reasons.append('incomplete_domains_no_zero_imputation')
            demand(json.loads(record['change_reasons']) == expected_reasons and bool(expected_reasons), 'Change reason is unsupported.')
        checks.append({'scope': 'independent_aggregation_tiers_missingness_and_change_accounting',
                       'compounds': len(keys), 'changes': len(changes), 'identity_review_compounds': int(review.sum())})
        replay = priority.integrate_priority(upstream)
        with tempfile.TemporaryDirectory(prefix='PlastPrior priority validation ') as folder:
            replay.write_reports(folder)
            demand(replay.manifest == manifest, 'Deterministic reconstruction differs.')
        checks.append({'scope': 'deterministic_reconstruction', 'files': len(manifest['output_sha256']) + 1})
        counts = manifest['counts']
    except (ValueError, KeyError, OSError, TypeError, StopIteration, ArithmeticError) as exc:
        differences.append({'scope': 'priority_validation', 'detail': str(exc)})
    report = {'stage': '7A', 'status': 'passed' if not differences else 'failed',
              'difference_count': len(differences), 'counts': counts, 'checks': checks,
              'comparison': 'Seven historical final fields and ten input scores; independent analysis aggregates, dual gates, missingness, unchanged upstream evidence and explicit changes. No ranking.'}
    pd.DataFrame(differences).to_csv(output_dir / 'priority_differences.csv', index=False, encoding='utf-8', lineterminator='\n')
    (output_dir / 'priority_validation_summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
