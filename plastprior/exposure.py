"""Stage 6B: traceable exposure screening with explicit evidence availability."""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import platform
import shutil

import pandas as pd

from . import _exposure_reference as reference
from .evidence import _json, _read_csv
from .evidence_specialists import require_prediction_isolation
from .exposure_inputs import csv_rows, json_rows, number, numeric_values, verify_inputs
from .inputs import _file_hash, resolve_data_root
from .lrtp import _verify_outputs

POLICY_PATH = Path(__file__).with_name('exposure_policy.json')
POLICY_HASH = _file_hash(POLICY_PATH)
POLICY = json.loads(POLICY_PATH.read_text(encoding='utf-8'))
IMPLEMENTATION_HASH = _file_hash(Path(__file__))
REFERENCE_HASH = _file_hash(Path(reference.__file__))
COMPONENTS = ['food_contact', 'human_biomonitoring', 'inventory', 'production', 'patent', 'literature']
DIMENSIONS = ['food_contact_and_biomonitoring', 'inventory', 'production', 'patent', 'literature']
OUTPUT_COLUMNS = reference.legacy_EXPOSURE_OUTPUT_COLUMNS


def threshold_score(value, dimension):
    """A missing value is not a valid observed zero."""
    numeric = number(value)
    if numeric is None:
        return None
    score = 0.0
    for threshold, level in POLICY['thresholds'][dimension]:
        if numeric >= Decimal(str(threshold)):
            score = float(level)
    return score


def production_score(value, presence):
    numeric = number(value)
    score = threshold_score(numeric, 'production')
    if numeric is not None and numeric > 0:
        score = max(0.5, score)
    if presence in reference.rules_POSITIVE_MARKET_PRESENCE_STATUSES:
        return max(0.5, score or 0.0)
    if numeric is not None or presence == 'confirmed_zero_quantity':
        return score if score is not None else 0.0
    return None


def human_detection_score(resolution):
    if resolution.get('policy_version') != reference.FCCHUMON_HUMAN_DETECTION_POLICY_VERSION:
        return None, 'specialist_detection_unavailable'
    if resolution.get('target_cas_mapping_status') == 'invalid_or_missing':
        return None, 'no_valid_query_cas'
    method = resolution.get('match_method')
    if method == 'cas_rejected_ambiguous_target_mapping':
        return None, 'ambiguous_target_cas_association'
    if method not in {'no_match', 'exact_one_to_one_cas'}:
        return None, 'unaccepted_human_detection_match_method'
    return float(resolution.get('detected') is True), ''


def aggregate_components(components):
    joint = (components['food_contact'] + components['human_biomonitoring']
             if all(components[k] is not None for k in ['food_contact', 'human_biomonitoring']) else None)
    dimensions = {'food_contact_and_biomonitoring': joint,
                  **{k: components[k] for k in DIMENSIONS[1:]}}
    available = sum(value is not None for value in dimensions.values())
    observed = sum(value for value in components.values() if value is not None)
    return {'Exposure_score': observed if available == 5 else None,
            'Exposure_observed_score': observed, 'Exposure_available_dimensions': available,
            'Exposure_complete': available == 5, 'dimension_scores': dimensions}


def count_observations(value, path=()):
    if isinstance(value, dict):
        return [r for key, child in value.items() for r in count_observations(child, path + (key,))]
    if isinstance(value, list):
        return [r for index, child in enumerate(value) for r in count_observations(child, path + (index,))]
    parsed = number(value)
    eligible = parsed is not None and parsed == parsed.to_integral_value()
    return [{'field_path': list(path), 'raw_value': value,
             'count': float(parsed) if eligible else None, 'eligible': eligible,
             'exclusion_reason': '' if eligible else 'invalid_nonnegative_integer_count'}]


def select_patent(curated, lite, external, gate):
    """Retain positive independent counts; failed zero correction remains missing."""
    observations = count_observations(curated)
    values = [Decimal(str(r['count'])) for r in observations if r['eligible']]
    curated_count = max(values, default=Decimal(0))
    lite_count = number(lite) or Decimal(0)
    source = 'PubChemLite' if lite_count > curated_count else 'curated_database_extract' if curated_count > 0 else None
    count = max(curated_count, lite_count) if source else None
    if gate and gate['eligible']:
        count = number(external.get('pubchem_patent_count'))
        source = 'PubChem PUG-REST PatentID'
    for record in observations:
        record['selected'] = bool(source == 'curated_database_extract' and record['eligible'] and Decimal(str(record['count'])) == count)
        if record['eligible'] and not record['selected']:
            record['exclusion_reason'] = 'not_selected_under_maximum_count_and_source_precedence'
    return {'count': float(count) if count is not None else None, 'source': source,
            'curated_observations': observations,
            'curated_count': float(curated_count), 'pubchemlite_count': float(lite_count),
            'external_audit_id': gate.get('audit_id') if gate else None,
            'external_exclusion_reasons': gate['exclusion_reasons'] if gate else ['no_frozen_query_record'],
            'unavailable_reason': '' if count is not None else 'no_validated_count_after_external_query_review'}


def historical_input_view(compounds):
    """Map source memberships and representative identifiers without model values."""
    columns = ['inchikey', 'cas_reported', 'name_resolved', 'db_extract_info',
               'GIC_inventory_listing_count', 'GIC_inventory_list_tags', 'GIC_inventory_data_status']
    view = compounds[columns].rename(columns={'inchikey': 'Inchikey_std', 'cas_reported': 'CAS', 'name_resolved': 'Name_std'}).copy()
    for source, field in [('fccmigex', 'db_FCCmigex'), ('fcchumon_s1', 'db_FCChumon_S1'), ('fcchumon_s2', 'db_FCChumon_S2')]:
        view[field] = [int(source in json.loads(text)) for text in compounds['source_tables_json']]
    return view


def selection_view(state):
    row = reference.market__selection_row(state)
    return {'policy_version': reference.market_SELECTION_POLICY_VERSION,
            'match_status': 'selected_numeric' if state.selected() is not None else 'no_eligible_numeric_evidence',
            'selected_record': reference.market__public_candidate(state.selected()),
            'rejected_candidate_counts': dict(sorted(state.rejected.items())),
            'selection_audit_file': 'production_market_selection_audit.jsonl',
            'summary_fields': {k: v for k, v in row.items() if k.startswith('Exposure_scale_')}}


def historical_selection_audit(state):
    return {'compound_key': state.inchikey, 'cas': state.cas, 'name': state.name,
            'selection_policy': reference.market_SELECTION_POLICY_VERSION,
            'selection_reason': 'maximum_historical_conservative_proxy_across_all_sources' if state.selected() is not None else 'no_eligible_numeric_evidence',
            'selected_record': reference.market__public_candidate(state.selected()),
            'best_candidate_by_source': {k: reference.market__public_candidate(v) for k, v in sorted(state.best_by_source.items())},
            'evidence_count': state.evidence_count, 'numeric_evidence_count': state.numeric_evidence_count,
            'eligible_numeric_count': state.eligible_numeric_count, 'sources': sorted(state.sources),
            'numeric_sources': sorted(state.numeric_sources), 'best_market_presence': state.best_presence,
            'rejected_candidate_counts': dict(sorted(state.rejected.items())),
            'canonical_evidence_files': ['production_volume_evidence.csv', 'market_presence_evidence.csv']}


def select_market(view, intake):
    """Reconstruct the historical selector and independently gate analysis candidates."""
    states = {role: {r['Inchikey_std']: reference.market_CompoundSelectionState(r['Inchikey_std'], r['CAS'], r['Name_std'])
                     for r in view.to_dict('records')} for role in ['historical', 'analysis']}
    source_positions = {role: {} for role in states}
    def add(key, candidate, audit_id, numeric, qualitative, presence, reasons):
        historical, analysis = states['historical'][key], states['analysis'][key]
        historical.add(candidate)
        if historical.best_by_source.get(candidate['source_id']) is candidate:
            source_positions['historical'][(key, candidate['source_id'])] = audit_id
        if numeric:
            analysis.add(candidate)
            if analysis.best_by_source.get(candidate['source_id']) is candidate:
                source_positions['analysis'][(key, candidate['source_id'])] = audit_id
        else:
            analysis.rejected.update(reasons)
        if qualitative and presence not in {'', 'unknown', 'not_found_in_source'}:
            analysis.sources.add(candidate['source_id'])
    for _, row in csv_rows(intake / 'market_source_records.csv'):
        key = row['inchikey'].strip().upper()
        if key not in states['historical']:
            continue
        add(key, reference.market__canonical_candidate(row), row['audit_id'], row['numeric_eligible'] == 'True',
            row['qualitative_eligible'] == 'True', row['market_presence'], json.loads(row['numeric_exclusion_reasons']))
    for row in view.to_dict('records'):
        key = row['Inchikey_std']
        for candidate in reference.market_iter_legacy_plastchem_candidates(row, key):
            scope, index = candidate['activity'], candidate['record_id'].rsplit(':', 1)[-1]
            add(key, candidate, f'legacy:{key}:{scope}:PlastChem:{index}', True, True, candidate['market_presence'], [])
    gates = {r['inchikey']: r for _, r in csv_rows(intake / 'market_gate_audit.csv')}
    for key, state in states['analysis'].items():
        state.best_presence = gates[key]['eligible_best_presence']
        state.evidence_count = states['historical'][key].evidence_count
        state.numeric_evidence_count = states['historical'][key].numeric_evidence_count
        if state.eligible_numeric_count != int(gates[key]['numeric_eligible_count']):
            raise ValueError('Exposure numeric selection disagrees with Stage 6A eligibility: ' + key)
    return states, source_positions


def _same(a, b):
    a = None if isinstance(a, str) and a == '' else a
    b = None if isinstance(b, str) and b == '' else b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        return Decimal(str(a)) == Decimal(str(b))
    return a == b


@dataclass
class ExposureResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    summary: pd.DataFrame
    impacts: pd.DataFrame
    audits: dict
    manifest: dict
    intake: Path
    data_root: Path
    candidate_choices: dict

    def write_reports(self, output_dir):
        out = Path(output_dir).resolve()
        root = self.intake.parent.parent
        if (out == self.intake or self.intake.is_relative_to(out) or out.is_relative_to(self.intake)
                or out.is_relative_to(self.data_root)
                or any(out.is_relative_to(root / stage) for stage in ['stage2', 'stage3', 'stage4', 'stage5'])):
            raise ValueError('Stage 6B must not overwrite Stage 6A inputs.')
        out.mkdir(parents=True, exist_ok=True)
        (out / 'exposure_scoring_manifest.json').unlink(missing_ok=True)
        files = []
        for name, frame in [('compound_exposure_scores', self.compounds), ('exposure_historical', self.historical),
                            ('exposure_score_summary', self.summary), ('exposure_score_changes', self.impacts)]:
            path = out / (name + '.csv')
            frame.to_csv(path, index=False, encoding='utf-8', lineterminator='\n')
            files.append(path)
        for name, rows in self.audits.items():
            path = out / (name + '.jsonl')
            with path.open('w', encoding='utf-8') as handle:
                for row in rows:
                    handle.write(_json(row) + '\n')
            files.append(path)
        for name in ['identity_review_source_links.jsonl']:
            path = out / name
            shutil.copyfile(self.intake / name, path)
            files.append(path)
        path = out / 'exposure_candidate_decisions.csv'
        fields = ['audit_id', 'inchikey', 'source_id', 'record_id', 'historical_eligible', 'analysis_eligible',
                  'historical_selection_reason', 'analysis_selection_reason']
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            for name in ['market_source_records.csv', 'legacy_production_records.csv']:
                for _, raw in csv_rows(self.intake / name):
                    key, source = raw['inchikey'].strip().upper(), raw['source_id']
                    if name == 'market_source_records.csv':
                        candidate = reference.market__canonical_candidate(raw)
                        eligible = (key in self.candidate_choices['historical'] and
                                    candidate['selected_tonnes_decimal'] is not None and
                                    candidate['identity_match_status'] in reference.market__ELIGIBLE_IDENTITY_STATUSES and
                                    reference.market_SOURCE_BY_ID.get(source) is not None and
                                    reference.market_SOURCE_BY_ID[source].selection_eligibility == 'eligible_compound_numeric')
                        analysis_eligible = raw['numeric_eligible'] == 'True'
                        excluded = raw['numeric_exclusion_reasons']
                    else:
                        eligible = analysis_eligible = raw['eligible'] == 'True'
                        excluded = raw['exclusion_reason']
                    record = {k: raw.get(k, '') for k in ['audit_id', 'inchikey', 'source_id', 'record_id']}
                    for role, accepted in [('historical', eligible), ('analysis', analysis_eligible)]:
                        choices = self.candidate_choices[role].get(key, {})
                        if not accepted:
                            reason = 'not_a_historical_numeric_candidate' if role == 'historical' else excluded
                        elif raw['audit_id'] == choices.get('selected'):
                            reason = 'selected_historical_maximum'
                        elif raw['audit_id'] == choices.get('sources', {}).get(source):
                            reason = 'not_retained_across_sources_value_status_metric_source_order'
                        else:
                            reason = 'not_retained_within_source_value_status_year_record_order'
                        record[role + '_eligible'] = accepted
                        record[role + '_selection_reason'] = reason
                    writer.writerow(record)
        files.append(path)
        self.manifest['output_sha256'] = {p.name: _file_hash(p) for p in files}
        (out / 'exposure_scoring_manifest.json').write_text(json.dumps(self.manifest, indent=2) + '\n', encoding='utf-8')


def integrate_exposure_scores(intake_results, data_root='data'):
    intake = Path(intake_results).resolve()
    root = intake.parent.parent
    data = resolve_data_root(data_root).resolve()
    paths = verify_inputs(data)
    upstream_paths = {'intake': intake / 'exposure_manifest.json',
                      'bt': root / 'stage5' / '5b' / 'bt_manifest.json'}
    hashes = {k: _file_hash(p) for k, p in upstream_paths.items()}
    upstream = {k: json.loads(p.read_text(encoding='utf-8')) for k, p in upstream_paths.items()}
    for k, path in upstream_paths.items():
        _verify_outputs(path.parent, upstream[k])
    if upstream['intake']['upstream_manifests_sha256']['bt'] != hashes['bt']:
        raise ValueError('Stage 6B inputs refer to different upstream runs.')
    for path, expected in [(POLICY_PATH, POLICY_HASH), (Path(__file__), IMPLEMENTATION_HASH),
                           (Path(reference.__file__), REFERENCE_HASH),
                           (Path(__file__).with_name('exposure_inputs.py'), upstream['intake']['implementation_sha256']),
                           (Path(__file__).with_name('exposure_inputs.json'), upstream['intake']['policy_sha256'])]:
        if _file_hash(path) != expected:
            raise ValueError('Exposure implementation or policy changed: ' + path.name)
    official_entry = POLICY['official_reference']
    official_path = data.joinpath(*official_entry['parts'])
    checkpoint = json.loads(paths['stage6_checkpoint'].read_text(encoding='utf-8'))
    if not any(a['artifact_id'] == official_entry['artifact_id'] and a['sha256'] == official_entry['sha256'] for a in checkpoint['artifacts']):
        raise ValueError('EPA compatibility input is not in the frozen checkpoint.')
    if _file_hash(official_path) != official_entry['sha256']:
        raise ValueError('Frozen EPA compatibility input changed.')
    compounds = _read_csv(upstream_paths['bt'].parent / 'compound_pbmt_hazard.csv')
    require_prediction_isolation(compounds)
    view = historical_input_view(compounds)
    keys = set(view['Inchikey_std'])
    states, positions = select_market(view, intake)
    historical_selections = {k: selection_view(v) for k, v in states['historical'].items()}
    archive_hashes = {Path(r['relative_path']).name: r['sha256'] for _, r in csv_rows(paths['production_inputs'])
                      if r['source_id'] == 'us_epa_cdr' and r['relative_path'].endswith('.zip')}
    official = reference.official_build_official_production_selections(view, official_path, source_archive_sha256=archive_hashes)['selections']
    lite = reference.legacy__load_pubchemlite_patent_lookup(paths['pubchemlite'])
    external = reference.external_load_patent_zero_corrections(paths['patent'], keys)['records']
    pubmed = reference.external_load_pubmed_query_audit(paths['pubmed'], keys)['records']
    historical = reference.legacy_add_exposure_columns(view.copy(), patent_lookup=lite,
                    official_production_selections=official, exposure_scale_selections=historical_selections,
                    patent_audit_records=external, pubmed_query_records=pubmed)
    historical = historical[['Inchikey_std'] + OUTPUT_COLUMNS].rename(columns={'Inchikey_std': 'inchikey'})
    historical['result_role'] = 'historical_reproduction_only'
    gates = {kind: {r['compound_key']: r for r in json_rows(intake / (kind + '_records.jsonl')) if r['compound_key'] in keys}
             for kind in ['patent', 'pubmed']}
    gic = {r['inchikey']: r for _, r in csv_rows(intake / 'gic_compound_audit.csv')}
    market_gates = {r['inchikey']: r for _, r in csv_rows(intake / 'market_gate_audit.csv')}
    lite_analysis = {}
    lite_links = {}
    for record in json_rows(intake / 'pubchemlite_patent_records.jsonl'):
        if not record['eligible']:
            continue
        key = record['compound_key']
        value = number(record['raw_fields']['Patent_Count'])
        if value is not None and (key not in lite_analysis or value > lite_analysis[key]):
            lite_analysis[key] = value
            lite_links[key] = record['audit_id']
    analysis_rows, decisions, changes = [], [], []
    historical_rows = historical.astype(object).where(pd.notna(historical), None).to_dict('records')
    for index, row in enumerate(view.to_dict('records')):
        key = row['Inchikey_std']
        selection = selection_view(states['analysis'][key])
        selection['policy_version'] = 'exposure-eligible-historical-maximum-v1'
        selection['summary_fields']['Exposure_scale_selection_policy'] = selection['policy_version']
        selection['selection_audit_file'] = 'exposure_analysis_decisions.jsonl'
        selected = selection['selected_record']
        selected_audit_id = positions['analysis'].get((key, selected['source_id'])) if selected else None
        inventory = gic[key]
        mapped = dict(row)
        mapped['GIC_inventory_listing_count'] = inventory['eligible_inventory_count']
        mapped['GIC_inventory_list_tags'] = '; '.join(json.loads(inventory['eligible_inventory_tags_json']))
        mapped['GIC_inventory_data_status'] = 'available' if inventory['eligibility_status'] == 'completed_lookup' else 'unavailable'
        inputs = reference.legacy__extract_exposure_inputs(mapped, 'db_extract_info', patent_lookup=lite_analysis,
                    official_production_selections={}, exposure_scale_selections={key: selection},
                    patent_audit_records=external, pubmed_query_records=pubmed)
        payload = json.loads(row['db_extract_info'])
        patent = select_patent(payload.get('exposure', {}).get('patent', {}), lite_analysis.get(key), external.get(key, {}), gates['patent'].get(key))
        patent['pubchemlite_audit_id'] = lite_links.get(key)
        literature_gate = gates['pubmed'].get(key)
        literature_count = float(number(pubmed[key]['pubmed_title_abstract_count'])) if literature_gate and literature_gate['eligible'] else None
        inputs.update({'Exposure_prod_total_tons': float(selected['selected_tonnes']) if selected else None,
                       'Exposure_prod_source': selected['source_name'] if selected else None,
                       'Exposure_prod_jurisdiction': selected['jurisdiction'] if selected else None,
                       'Exposure_prod_reporting_year': selected['reporting_year'] or selected['reporting_period'] if selected else None,
                       'Exposure_prod_value_status': selected['value_status'] if selected else None,
                       'Exposure_patent_count': patent['count'], 'Exposure_patent_source': patent['source'],
                       'Exposure_patent_data_status': 'available' if patent['count'] is not None else 'unavailable',
                       'Exposure_literature_count': literature_count, 'Exposure_pubmed_title_abstract_count': literature_count,
                       'Exposure_literature_data_status': 'available' if literature_count is not None else 'unavailable',
                       'Exposure_patent_policy': 'eligible-patent-zero-correction-v1'})
        human_score, human_reason = human_detection_score(payload.get('fcchumon_resolution', {}))
        if human_score is None:
            inputs['Exposure_FCChumon_detection_data_status'] = 'unavailable'
            for field in ['Exposure_FCChumon_S1_detected', 'Exposure_FCChumon_S2_detected', 'Exposure_FCChumon_detection_count']:
                inputs[field] = None
        components = {'food_contact': float(inputs['Exposure_FCCmigex_listed']),
                      'human_biomonitoring': human_score,
                      'inventory': threshold_score(inventory['eligible_inventory_count'], 'inventory') if inventory['eligibility_status'] == 'completed_lookup' else None,
                      'production': production_score(selected['selected_tonnes'] if selected else None, states['analysis'][key].best_presence),
                      'patent': threshold_score(patent['count'], 'patent'), 'literature': threshold_score(literature_count, 'literature')}
        aggregate = aggregate_components(components)
        reasons = {'food_contact': '', 'human_biomonitoring': human_reason,
                   'inventory': '' if components['inventory'] is not None else inventory['eligibility_status'],
                   'production': '' if components['production'] is not None else 'no_eligible_numeric_or_interpretable_qualitative_evidence',
                   'patent': patent['unavailable_reason'],
                   'literature': '' if literature_count is not None else 'no_validated_pubmed_query'}
        decision = {'compound_key': key, 'result_role': 'analysis_after_eligibility_audit',
                    'production_selection': selection, 'selected_market_audit_id': selected_audit_id,
                    'best_candidate_by_source': {k: reference.market__public_candidate(v) for k, v in sorted(states['analysis'][key].best_by_source.items())},
                    'market_gate': market_gates[key], 'gic_eligibility': inventory, 'patent_selection': patent,
                    'literature_query': literature_gate, 'fcchumon_resolution': payload.get('fcchumon_resolution'),
                    'source_tables_json': compounds.iloc[index]['source_tables_json'],
                    'component_scores': components, 'component_unavailable_reasons': reasons,
                    'dimension_scores': aggregate['dimension_scores'], 'complete_total_required': True,
                    'upstream_manifest_sha256': hashes['intake'], 'model_predictions_used': False}
        outputs = {k: inputs[k] for k in OUTPUT_COLUMNS if k in inputs}
        outputs.update({f'Exposure_{k}_score': v for k, v in components.items()})
        outputs.update({k: v for k, v in aggregate.items() if k != 'dimension_scores'})
        outputs['Exposure_score_basis'] = '|'.join('inventory_presence_proxy' if k == 'inventory' else k for k, v in components.items() if v is not None and v > 0) or None
        outputs['Exposure_evidence'] = _json(decision)
        outputs['exposure_result_role'] = 'analysis_after_eligibility_audit'
        outputs['Exposure_missing_dimensions'] = _json([k for k, v in aggregate['dimension_scores'].items() if v is None])
        for component, value in components.items():
            outputs[f'exposure_{component}_available'] = value is not None
            outputs[f'exposure_{component}_unavailable_reason'] = reasons[component]
        analysis_rows.append(outputs)
        decisions.append(decision)
        old = historical_rows[index]
        for column in OUTPUT_COLUMNS:
            before, after = old[column], outputs.get(column)
            if _same(before, after):
                continue
            why = []
            if column.startswith(('Exposure_scale_', 'Exposure_prod', 'Exposure_production')):
                if market_gates[key]['presence_changed_by_gate'] == 'True': why.append('qualitative_identity_or_source_gate')
                if states['historical'][key].eligible_numeric_count != states['analysis'][key].eligible_numeric_count: why.append('invalid_quantity_exclusion')
                if after is None: why.append('unavailable_is_not_zero')
                if not why: why.append('eligibility_audit_provenance')
            elif column.startswith('Exposure_FCChumon') or column == 'Exposure_human_biomonitoring_score':
                why.append(human_reason or 'qualified_human_detection_provenance')
            elif column.startswith('Exposure_inventory'):
                why.append('gic_name_or_direct_support_gate' if inventory['eligibility_status'] != 'completed_lookup' else 'eligible_inventory_tag_representation')
            elif column.startswith('Exposure_patent'):
                why.append('unavailable_is_not_zero' if patent['count'] is None else 'qualified_patent_selection_provenance')
                if gates['patent'].get(key, {}).get('raw_fields', {}).get('error_message', '').strip(): why.append('patent_query_error')
            elif column.startswith(('Exposure_literature', 'Exposure_pubmed')):
                why.append('unavailable_pubmed_is_not_zero')
            elif column == 'Exposure_score':
                why.append('incomplete_exposure_total' if not aggregate['Exposure_complete'] else 'eligible_component_score_change')
            else:
                why.append('eligibility_audit_provenance' if column == 'Exposure_evidence' else 'eligible_component_basis_change')
            changes.append({'inchikey': key, 'field': column, 'historical_value_json': _json(before),
                            'analysis_value_json': _json(after), 'change_reasons_json': _json(why),
                            'qsar_identity_status': compounds.iloc[index]['qsar_identity_status']})
    analysis = compounds.copy()
    for column in analysis_rows[0]:
        analysis[column] = [r[column] for r in analysis_rows]
    require_prediction_isolation(analysis)
    summary = []
    for role, frame in [('historical', historical), ('analysis', analysis)]:
        for column in [f'Exposure_{k}_score' for k in COMPONENTS] + ['Exposure_score']:
            summary.append({'view': role, 'field': column, 'available': int(frame[column].notna().sum()),
                            'unavailable': int(frame[column].isna().sum()), 'zero': int(frame[column].eq(0).sum())})
    for k, path in upstream_paths.items():
        if _file_hash(path) != hashes[k]: raise ValueError('Exposure upstream manifest changed.')
        _verify_outputs(path.parent, upstream[k])
    verify_inputs(data)
    for path, expected in [(POLICY_PATH, POLICY_HASH), (Path(__file__), IMPLEMENTATION_HASH), (Path(reference.__file__), REFERENCE_HASH), (official_path, official_entry['sha256'])]:
        if _file_hash(path) != expected: raise ValueError('Exposure implementation or input changed during scoring.')
    manifest = {'schema_version': 1, 'stage': '6B', 'scope': POLICY['scope'], 'policy_sha256': POLICY_HASH,
                'implementation_sha256': IMPLEMENTATION_HASH, 'reference_implementation_sha256': REFERENCE_HASH,
                'upstream_manifests_sha256': hashes, 'official_reference_sha256': official_entry['sha256'],
                'counts': {'compounds': len(compounds), 'historical_fields': len(OUTPUT_COLUMNS),
                           'identity_review_compounds': int(compounds['qsar_identity_status'].eq('review_required').sum()),
                           'complete_analysis_totals': int(analysis['Exposure_complete'].sum()),
                           'incomplete_analysis_totals': int((~analysis['Exposure_complete']).sum()), 'field_changes': len(changes)},
                'rules': POLICY['rules'], 'runtime': {'python': platform.python_version(), 'pandas': pd.__version__}}
    audits = {'exposure_historical_selection': [historical_selection_audit(states['historical'][k]) for k in sorted(keys)],
              'exposure_historical_evidence': [{'compound_key': r['inchikey'], **json.loads(r['Exposure_evidence'])} for r in historical_rows],
              'exposure_analysis_decisions': decisions}
    choices = {}
    for role, mapping in states.items():
        choices[role] = {}
        for key, state in mapping.items():
            selected = state.selected()
            choices[role][key] = {'selected': positions[role].get((key, selected['source_id'])) if selected else None,
                                  'sources': {source: positions[role][(key, source)] for source in state.best_by_source}}
    return ExposureResult(analysis, historical, pd.DataFrame(summary), pd.DataFrame(changes), audits, manifest, intake, data, choices)
