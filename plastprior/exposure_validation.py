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


def compare_exposure_scores(baseline, results, output_dir, upstream_results=None, data_root=None):
    """Validate 63 historical fields and independently audit analysis score changes."""
    from . import exposure as scoring
    from .validation import _verify_hash, _compare_qsar_frame, _compare_evidence

    baseline, results, output_dir = map(lambda p: Path(p).resolve(), [baseline, results, output_dir])
    intake = Path(upstream_results).resolve() if upstream_results else results.parent / '6a'
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks, counts = [], [], {}
    def demand(condition, message):
        if not condition:
            raise ValueError(message)
    def compare_json(a, b, key, scope):
        for diff in _compare_evidence(json.dumps(a), json.dumps(b), key):
            diff['scope'] = scope
            diff['field'] = diff['field'].replace('LRTP_evidence', scope, 1)
            differences.append(diff)
    def numeric(text):
        if text is None or str(text).strip() == '':
            return None
        value = Decimal(str(text))
        return value if value.is_finite() else None
    def band(value, cutoffs):
        if value is None:
            return None
        return max([0] + [score for cutoff, score in cutoffs if value >= cutoff])
    try:
        previous = compare_exposure_inputs(baseline, intake, output_dir / 'stage6a', data_root=data_root)
        demand(previous['status'] == 'passed', 'Stage 6A and upstream regression failed.')
        manifest = json.loads((results / 'exposure_scoring_manifest.json').read_text(encoding='utf-8'))
        _verify_outputs(results, manifest)
        for path, field in [(scoring.POLICY_PATH, 'policy_sha256'), (Path(scoring.__file__), 'implementation_sha256'),
                            (Path(scoring.reference.__file__), 'reference_implementation_sha256')]:
            _verify_hash(path, manifest[field])
        root = intake.parent.parent
        bt = root / 'stage5' / '5b'
        for key, path in [('bt', bt / 'bt_manifest.json'), ('intake', intake / 'exposure_manifest.json')]:
            _verify_hash(path, manifest['upstream_manifests_sha256'][key])
        run = json.loads((baseline / 'run_manifest.json').read_text(encoding='utf-8'))
        checkpoint = baseline / run['stages']['6']['checkpoint']
        _verify_hash(checkpoint, run['stages']['6']['checkpoint_sha256'])
        artifacts = {r['artifact_id']: r for r in json.loads(checkpoint.read_text(encoding='utf-8'))['artifacts']}
        needed = ['compound_inventory_with_exposure_csv', 'production_market_selection_audit_jsonl', 'official_us_epa_production_by_cas_csv']
        for name in needed:
            _verify_hash(baseline / artifacts[name]['path'], artifacts[name]['sha256'])
        _verify_hash(resolve_data_root('data' if data_root is None else data_root).joinpath(*scoring.POLICY['official_reference']['parts']),
                     artifacts['official_us_epa_production_by_cas_csv']['sha256'])
        old = pd.read_csv(baseline / artifacts['compound_inventory_with_exposure_csv']['path'],
                          usecols=['Inchikey_std'] + scoring.OUTPUT_COLUMNS, dtype=str, keep_default_na=False,
                          encoding='utf-8').rename(columns={'Inchikey_std': 'inchikey'})
        historical = _read_csv(results / 'exposure_historical.csv')
        actual = _read_csv(results / 'compound_exposure_scores.csv')
        prior = _read_csv(bt / 'compound_pbmt_hazard.csv')
        fields = [c for c in scoring.OUTPUT_COLUMNS if c != 'Exposure_evidence']
        numeric_fields = {c for c in fields if any(w in c for w in ['_count', '_score', '_tonnes', '_tons', '_listed', '_detected', '_has_']) and not c.endswith('_basis')}
        differences.extend(_compare_qsar_frame(old, historical, 'inchikey', {c:c for c in fields}, numeric_fields, 'historical_exposure_fields'))
        old_by_key, historical_by_key = old.set_index('inchikey'), historical.set_index('inchikey')
        for key in old_by_key.index:
            compare_json(json.loads(old_by_key.at[key, 'Exposure_evidence']), json.loads(historical_by_key.at[key, 'Exposure_evidence']), key, 'historical_exposure_evidence')
        checks.append({'scope': 'historical_field_comparison', 'compounds': len(old), 'fields': len(scoring.OUTPUT_COLUMNS)})
        differences.extend(_compare_qsar_frame(prior, actual, 'inchikey', {c:c for c in prior if c != 'inchikey'}, set(), 'unchanged_upstream_fields'))
        require_prediction_isolation(actual)
        demand(historical['result_role'].eq('historical_reproduction_only').all(), 'Incorrect historical result role.')
        demand(actual['exposure_result_role'].eq('analysis_after_eligibility_audit').all(), 'Incorrect analysis result role.')
        demand(not any('priority' in c.lower() or 'rank' in c.lower() for c in actual.columns), 'Unexpected prioritisation output.')
        historic_selections = {r['compound_key']:r for r in json_rows(baseline / artifacts['production_market_selection_audit_jsonl']['path'])}
        for row in json_rows(results / 'exposure_historical_selection.jsonl'):
            compare_json(historic_selections[row['compound_key']], row, row['compound_key'], 'historical_market_selection')
        market = _read_csv(intake / 'market_gate_audit.csv').set_index('inchikey')
        gic = _read_csv(intake / 'gic_compound_audit.csv').set_index('inchikey')
        external = {name: {r['compound_key']:r for r in json_rows(intake / (name + '_records.jsonl'))} for name in ['patent', 'pubmed']}
        lite = {}
        for row in json_rows(intake / 'pubchemlite_patent_records.jsonl'):
            if row['eligible']:
                key = row['compound_key'];value = numeric(row['raw_fields']['Patent_Count'])
                lite[key] = max(lite.get(key, Decimal(0)), value)
        seen, selected_ids, expected_changes = set(), {}, set()
        actual_by_key = actual.set_index('inchikey')
        for decision in json_rows(results / 'exposure_analysis_decisions.jsonl'):
            key = decision['compound_key']
            demand(key not in seen and key in actual_by_key.index, 'Invalid analysis decision coverage.')
            seen.add(key)
            row = actual_by_key.loc[key]
            demand(json.loads(row['Exposure_evidence']) == decision, 'Analysis table and decision ledger disagree.')
            payload = json.loads(row['db_extract_info'])
            selected = decision['production_selection']['selected_record']
            # The frozen run selected no negative quantities. Removing invalid
            # candidates must not silently replace a historical numeric winner.
            compare_json(historic_selections[key]['selected_record'], selected, key, 'unchanged_numeric_winner')
            if selected:
                selected_ids[decision['selected_market_audit_id']] = key
            quantity = numeric(selected['selected_tonnes']) if selected else None
            presence = market.at[key, 'eligible_best_presence']
            if quantity is not None and quantity >= 100000: production = 2.0
            elif quantity is not None and quantity >= 1000: production = 1.0
            elif ((quantity is not None and quantity > 0) or presence in {'confirmed_positive_quantity', 'confirmed_confidential_quantity', 'confirmed_record_no_public_quantity', 'historical_record'}): production = .5
            elif quantity is not None or presence == 'confirmed_zero_quantity': production = 0.0
            else: production = None
            inventory = band(numeric(gic.at[key, 'eligible_inventory_count']), [(1,.5),(2,1),(4,2)]) if gic.at[key, 'eligibility_status'] == 'completed_lookup' else None
            curated = []
            def visit(value):
                if isinstance(value, dict):
                    for child in value.values(): visit(child)
                elif isinstance(value, list):
                    for child in value: visit(child)
                elif value is not None and not isinstance(value, bool):
                    try: n = Decimal(str(value).replace(',', ''))
                    except InvalidOperation: return
                    if n.is_finite() and n >= 0 and n == n.to_integral_value(): curated.append(n)
            visit(payload.get('exposure', {}).get('patent', {}))
            fallback = max(curated + [lite.get(key, Decimal(0))])
            patent_record = external['patent'].get(key)
            patent_count = numeric(patent_record['raw_fields']['pubchem_patent_count']) if patent_record and patent_record['eligible'] else fallback if fallback > 0 else None
            literature_record = external['pubmed'][key]
            literature_count = numeric(literature_record['raw_fields']['pubmed_title_abstract_count']) if literature_record['eligible'] else None
            human = payload.get('fcchumon_resolution', {})
            expected = {'food_contact': float('fccmigex' in json.loads(row['source_tables_json'])),
                        'human_biomonitoring': float(human.get('detected') is True) if (human.get('policy_version') == 'fcchumon-human-detection-one-to-one-cas-v1'
                            and human.get('target_cas_mapping_status') != 'invalid_or_missing'
                            and human.get('match_method') in {'no_match','exact_one_to_one_cas'}) else None,
                        'inventory': inventory, 'production': production,
                        'patent': band(patent_count, [(1,.5),(1000,1),(10000,2)]),
                        'literature': band(literature_count, [(1,.5),(5,1),(20,2)])}
            for component, value in expected.items():
                observed = numeric(row['Exposure_' + component + '_score'])
                demand(observed == (None if value is None else Decimal(str(value))), 'Analysis score differs from independently applied gate/threshold: ' + key + ':' + component)
                demand(row['exposure_' + component + '_available'] == str(value is not None), 'Component availability differs from score missingness.')
                demand(bool(row['exposure_' + component + '_unavailable_reason']) == (value is None), 'Missing component reason is inconsistent.')
            joint = None if any(expected[k] is None for k in ['food_contact', 'human_biomonitoring']) else expected['food_contact'] + expected['human_biomonitoring']
            dimensions = {'food_contact_and_biomonitoring':joint, **{k:expected[k] for k in ['inventory','production','patent','literature']}}
            coverage = sum(v is not None for v in dimensions.values())
            observed_sum = sum(v for v in expected.values() if v is not None)
            demand(int(row['Exposure_available_dimensions']) == coverage, 'Incorrect exposure coverage.')
            demand(numeric(row['Exposure_observed_score']) == Decimal(str(observed_sum)), 'Incorrect observed-component sum.')
            demand(numeric(row['Exposure_score']) == (Decimal(str(observed_sum)) if coverage == 5 else None), 'Incomplete total was zero-filled or renormalised.')
            demand(row['Exposure_complete'] == str(coverage == 5), 'Incorrect completeness flag.')
            demand(json.loads(row['Exposure_missing_dimensions']) == [k for k,v in dimensions.items() if v is None], 'Missing dimension list differs.')
            demand(not decision['model_predictions_used'], 'Predictions entered exposure scoring.')
            for column in scoring.OUTPUT_COLUMNS:
                a,b=historical_by_key.at[key,column],row[column]
                equal = (a==b) or (column in numeric_fields and a and b and numeric(a)==numeric(b))
                if not equal: expected_changes.add((key,column))
        demand(seen == set(actual['inchikey']), 'Incomplete analysis decisions.')
        selected_seen = set()
        for _, row in csv_rows(results / 'exposure_candidate_decisions.csv'):
            if row['analysis_selection_reason'] == 'selected_historical_maximum':
                demand(row['analysis_eligible'] == 'True' and selected_ids.get(row['audit_id']) == row['inchikey'], 'An ineligible or unrelated candidate was selected.')
                selected_seen.add(row['audit_id'])
        demand(selected_seen == set(selected_ids), 'Selected candidate lineage is incomplete.')
        changes = _read_csv(results / 'exposure_score_changes.csv')
        observed_changes=set(zip(changes['inchikey'],changes['field']))
        demand(len(changes)==len(observed_changes) and observed_changes==expected_changes, 'Field-change ledger omits changes or invents differences.')
        for row in changes.to_dict('records'):
            demand(bool(json.loads(row['change_reasons_json'])), 'A score/input change has no reason.')
            for value_field, frame in [('historical_value_json', historical_by_key), ('analysis_value_json', actual_by_key)]:
                value = json.loads(row[value_field])
                expected = frame.at[row['inchikey'], row['field']]
                if row['field'] in numeric_fields:
                    demand(numeric(value) == numeric(expected), 'Change ledger numeric value differs from output.')
                else:
                    demand(('' if value is None else str(value)) == expected, 'Change ledger field value differs from output.')
        demand(_file_hash(results/'identity_review_source_links.jsonl')==_file_hash(intake/'identity_review_source_links.jsonl'), 'Model-review source links changed.')
        checks.append({'scope':'independent_analysis_thresholds_and_missingness','compounds':len(seen),'fields_with_documented_changes':len(changes), 'selected_candidate_links':len(selected_seen)})
        replay=scoring.integrate_exposure_scores(intake, 'data' if data_root is None else data_root)
        with tempfile.TemporaryDirectory(prefix='PlastPrior exposure scoring validation ') as folder:
            replay.write_reports(folder)
            demand(replay.manifest == manifest, 'Exposure scoring differs from deterministic reconstruction.')
        checks.append({'scope':'deterministic_reconstruction','files':len(manifest['output_sha256'])+1})
        counts=manifest['counts']
    except (ValueError,KeyError,OSError,TypeError,InvalidOperation) as exc:
        differences.append({'scope':'exposure_scoring_validation','key':'','field':'precondition','expected':'valid frozen inputs and declared eligibility changes','actual':str(exc)})
    report={'stage':'6B','status':'passed' if not differences else 'failed','difference_count':len(differences),'counts':counts,'checks':checks,
            'comparison':'All 63 historical fields and recursive evidence; independent analysis thresholds, missingness, identity isolation, source selection and explicit change accounting.'}
    pd.DataFrame(differences,columns=['scope','key','field','expected','actual']).to_csv(output_dir/'exposure_scoring_differences.csv',index=False,encoding='utf-8',lineterminator='\n')
    (output_dir/'exposure_scoring_validation_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
