"""Independent frozen-input and regression checks for Stage 6A."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import csv
from itertools import zip_longest
import json
from pathlib import Path
import tempfile

import pandas as pd

from .inputs import _file_hash, resolve_data_root
from .exposure_inputs import DEFAULT_POLICY, POLICY, POLICY_HASH, csv_rows, json_rows, integrate_exposure_evidence, verify_inputs
from .evidence import _read_csv
from .evidence_specialists import require_prediction_isolation
from .lrtp import _verify_outputs


def compare_exposure_inputs(baseline, results, output_dir, upstream_results=None, data_root=None):
    """Compare source fields verbatim; separate intended eligibility changes."""
    from .validation import compare_bt_hazard, _verify_hash

    baseline, results, output_dir = map(lambda p: Path(p).resolve(), [baseline, results, output_dir])
    root = results.parent.parent
    bt = Path(upstream_results).resolve() if upstream_results else root / 'stage5' / '5b'
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks = [], []
    counts = {}
    def demand(condition, message):
        if not condition:
            raise ValueError(message)
    try:
        previous = compare_bt_hazard(baseline, bt, output_dir / 'stage5b')
        demand(previous['status'] == 'passed', 'Stage 5B and upstream regression failed.')
        manifest = json.loads((results / 'exposure_manifest.json').read_text(encoding='utf-8'))
        _verify_outputs(results, manifest)
        _verify_hash(DEFAULT_POLICY, manifest['policy_sha256'])
        _verify_hash(Path(__file__).with_name('exposure_inputs.py'), manifest['implementation_sha256'])
        demand(not manifest['new_scores_computed'] and not manifest['numeric_maxima_selected'], 'Stage 6A scope changed.')
        paths = verify_inputs(resolve_data_root("data" if data_root is None else data_root))
        _verify_hash(baseline / 'run_manifest.json', next(e['sha256'] for e in POLICY['inputs'] if e['id'] == 'run_manifest'))
        run = json.loads((baseline / 'run_manifest.json').read_text(encoding='utf-8'))
        checkpoint_path = baseline / run['stages']['6']['checkpoint']
        _verify_hash(checkpoint_path, run['stages']['6']['checkpoint_sha256'])
        checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        artifacts = {a['artifact_id']: a for a in checkpoint['artifacts']}
        for entry in POLICY['inputs']:
            if 'artifact_id' in entry:
                record = artifacts[entry['artifact_id']]
                _verify_hash(baseline / record['path'], record['sha256'])
                demand(record['sha256'] == _file_hash(paths[entry['id']]), 'Copied derived input differs from the frozen run.')
        actual = iter(csv_rows(results / 'market_source_records.csv'))
        total = 0
        numeric_exclusions, quantity_anomalies = Counter(), []
        registry = {r['source_id']: r for _, r in csv_rows(paths['registry'])}
        for kind in ['production', 'market']:
            for ordinal, raw in csv_rows(paths[kind]):
                _, observed = next(actual)
                for column in POLICY['canonical_fields']:
                    demand(raw[column] == observed[column], f'Canonical field changed: {kind}:{ordinal}:{column}')
                demand(observed['source_table'] == kind and observed['source_row_number'] == str(ordinal), 'Canonical row lineage or multiplicity changed.')
                demand(observed['input_sha256'] == manifest['input_sha256'][kind], 'Incorrect source fingerprint.')
                demand(observed['audit_id'] == f'{kind}:{ordinal}', 'Incorrect canonical audit identifier.')
                if raw['identity_match_status'] == 'ambiguous_dashboard_cas_mapping':
                    demand(observed['qualitative_eligible'] == 'False' and observed['numeric_eligible'] == 'False', 'Ambiguous identity bypassed the exposure gate.')
                if 'invalid_quantity_bound' in json.loads(observed['numeric_exclusion_reasons']):
                    finite_bounds = []
                    for column in ['quantity_lower_tonnes', 'quantity_upper_tonnes']:
                        try:
                            value = Decimal(raw[column])
                        except InvalidOperation:
                            continue
                        if value.is_finite():
                            finite_bounds.append(value)
                    previously_numeric = (bool(finite_bounds)
                                          and raw['identity_match_status'] in POLICY['eligible_identity_statuses']
                                          and registry[raw['source_id']]['selection_eligibility'] == 'eligible_compound_numeric'
                                          and 'outside_compound_universe' not in observed['numeric_exclusion_reasons'])
                    demand(observed['numeric_eligible'] == 'False', 'Invalid quantity became numerically eligible.')
                    numeric_exclusions[raw['inchikey']] += int(previously_numeric)
                    quantity_anomalies.append({'audit_id': observed['audit_id'], 'inchikey': raw['inchikey'],
                                               'source_id': raw['source_id'], 'source_record_id': raw['source_record_id'],
                                               'quantity_raw': raw['quantity_raw'],
                                               'quantity_lower_tonnes': raw['quantity_lower_tonnes'],
                                               'quantity_upper_tonnes': raw['quantity_upper_tonnes'],
                                               'historically_numeric_eligible': previously_numeric,
                                               'numeric_eligible': False,
                                               'exclusion_reasons': observed['numeric_exclusion_reasons']})
                total += 1
        pd.DataFrame(quantity_anomalies).to_csv(output_dir / 'quantity_anomalies.csv', index=False, encoding='utf-8', lineterminator='\n')
        demand(next(actual, None) is None, 'Unexpected extra canonical observations.')
        checks.append({'scope': 'canonical_fields_verbatim', 'records': total, 'fields_per_record': len(POLICY['canonical_fields'])})
        for kind, name in [('patent', 'patent_records.jsonl'), ('pubmed', 'pubmed_records.jsonl'), ('pubchemlite', 'pubchemlite_patent_records.jsonl')]:
            total = 0
            for source, audit in zip_longest(csv_rows(paths[kind]), json_rows(results / name)):
                demand(source is not None and audit is not None, 'External row multiplicity changed: ' + kind)
                ordinal, raw = source
                demand(raw == audit['raw_fields'], 'External source field changed: ' + kind)
                demand(audit['audit_id'] == f'{kind}:{ordinal}' and audit['input_sha256'] == manifest['input_sha256'][kind], 'External source lineage changed.')
                total += 1
            checks.append({'scope': kind + '_raw_fields_verbatim', 'records': total})
        # Historical evidence counts and qualitative states come from the OLD audit,
        # not from a replay of the new gate implementation.
        old_artifact = artifacts['production_market_selection_audit_jsonl']
        old_path = baseline / old_artifact['path']
        _verify_hash(old_path, old_artifact['sha256'])
        market = _read_csv(results / 'market_gate_audit.csv').set_index('inchikey')
        seen, numeric_changes = set(), []
        for old in json_rows(old_path):
            key = old['compound_key']
            demand(key not in seen and key in market.index, 'Historical market identity coverage differs.')
            seen.add(key)
            new = market.loc[key]
            demand(new['historical_best_presence'] == old['best_market_presence'], 'Historical qualitative state differs: ' + key)
            demand(int(new['historical_evidence_count']) == old['evidence_count'], 'Historical evidence count differs: ' + key)
            observed_numeric = int(new['numeric_eligible_count'])
            demand(old['eligible_numeric_count'] - observed_numeric == numeric_exclusions[key],
                   'Unexplained numeric-eligibility change: ' + key)
            numeric_changes.append({'inchikey': key, 'historical_numeric_eligible_count': old['eligible_numeric_count'],
                                    'analysis_numeric_eligible_count': observed_numeric,
                                    'excluded_invalid_quantity_count': numeric_exclusions[key],
                                    'reason': 'invalid_quantity_bound' if numeric_exclusions[key] else 'unchanged'})
        demand(seen == set(market.index), 'Incomplete historical market comparison.')
        pd.DataFrame(numeric_changes).to_csv(output_dir / 'numeric_eligibility_changes.csv', index=False, encoding='utf-8', lineterminator='\n')
        checks.append({'scope': 'numeric_eligibility_change_accounting', 'quantity_anomaly_records': len(quantity_anomalies),
                       'formerly_eligible_invalid_quantities': sum(numeric_exclusions.values()),
                       'affected_compounds': sum(v > 0 for v in numeric_exclusions.values())})
        checks.append({'scope': 'old_market_audit', 'compounds': len(seen), 'fields': ['best_market_presence', 'evidence_count']})
        prior = _read_csv(bt / 'compound_pbmt_hazard.csv')
        require_prediction_isolation(prior)
        view = _read_csv(results / 'compound_exposure_evidence.csv')
        demand(len(view) == len(prior) and view['inchikey'].tolist() == prior['inchikey'].tolist(), 'Compound coverage or order changed.')
        for column in set(view.columns) & set(prior.columns):
            demand(view[column].tolist() == prior[column].tolist(), 'Upstream annotation changed: ' + column)
        demand(not any('score' in c.lower() for c in view.columns), 'An exposure score entered Stage 6A.')
        demand(view['result_role'].eq('exposure_evidence_eligibility_only').all(), 'Ambiguous Stage 6A output role.')
        review = prior[prior['qsar_identity_status'].eq('review_required')]
        demand(len(review) == 15, 'Identity-review cohort changed.')
        demand(_file_hash(bt / 'identity_review_source_links.jsonl') == _file_hash(results / 'identity_review_source_links.jsonl'), 'Identity-review source links changed.')
        gic = _read_csv(results / 'gic_compound_audit.csv').set_index('inchikey')
        tag_counts = Counter()
        for row in json_rows(results / 'gic_tag_eligibility.jsonl'):
            expected_support = [s['sid'] for s in row['source_records'] if row['list_tag'] in s['local_list_tags']]
            demand(expected_support == row['direct_support_sids'], 'GIC direct source support changed.')
            expected = (row['match_method'] == 'cid_bridge' and bool(expected_support)
                        and not row['metadata']['is_auxiliary']
                        and row['metadata']['regulatory_action_class'] == 'inventory_registration_or_use_only')
            demand(row['eligible'] == expected, 'GIC eligibility bypassed identity, direct support or classification gate.')
            if row['eligible']:
                tag_counts[row['compound_key']] += 1
        for key, row in gic.iterrows():
            if row['match_method'] == 'chemical_name':
                demand(row['eligible_inventory_count'] == '' and not tag_counts[key], 'Name-only GIC evidence became eligible or missingness became zero.')
            elif row['eligibility_status'] == 'completed_lookup':
                demand(int(row['eligible_inventory_count']) == tag_counts[key], 'GIC compound count differs from tag audit.')
        shared = gic.loc['GUUHFMWKWLOQMM-NTCAYCPXSA-N']
        demand(int(shared['eligible_inventory_count']) == 12, 'Directly supported inventory tags were lost in the shared-identifier case.')
        demand(gic['match_method'].eq('chemical_name').sum() == 1132, 'GIC name-review cohort changed.')
        checks.append({'scope': 'identity_and_gic_gates', 'model_review_compounds': len(review), 'name_review_compounds': 1132,
                       'shared_identifier_directly_supported_inventory_tags': 12})
        expected_links = (r for r in json_rows(root / 'stage4' / 'basic_evidence_audit.jsonl') if r.get('field_path', '').startswith('exposure.'))
        for old, new in zip_longest(expected_links, json_rows(results / 'exposure_source_links.jsonl')):
            demand(old == new, 'Curated exposure source observation or exclusion changed.')
        replay = integrate_exposure_evidence(bt, data_root)
        with tempfile.TemporaryDirectory(prefix='PlastPrior exposure validation ') as folder:
            replay.write_reports(folder)
            demand(replay.manifest == manifest, 'Exposure output differs from deterministic reconstruction.')
        checks.append({'scope': 'deterministic_reconstruction', 'files': len(manifest['output_sha256']) + 1})
        counts = manifest['counts']
    except (ValueError, KeyError, OSError, TypeError, StopIteration, csv.Error) as exc:
        differences.append({'scope': 'exposure_validation', 'detail': str(exc)})
    report = {'stage': '6A', 'status': 'passed' if not differences else 'failed', 'difference_count': len(differences),
              'counts': counts, 'checks': checks,
              'comparison': 'Verbatim frozen input fields and record multiplicity; historical qualitative states and evidence counts; intended eligibility changes reported separately. No exposure scoring validation is claimed.'}
    pd.DataFrame(differences, columns=['scope', 'detail']).to_csv(output_dir / 'exposure_differences.csv', index=False, encoding='utf-8', lineterminator='\n')
    (output_dir / 'exposure_validation_summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
