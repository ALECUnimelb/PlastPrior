"""Stage 7A: zero-contribution aggregation with independent evidence completeness."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import platform
import shutil

import pandas as pd

from .evidence import _json, _read_csv
from .evidence_specialists import require_prediction_isolation
from .inputs import _file_hash
from .lrtp import _verify_outputs

POLICY_PATH = Path(__file__).with_name('priority_policy.json')
POLICY = json.loads(POLICY_PATH.read_text(encoding='utf-8'))
POLICY_HASH = _file_hash(POLICY_PATH)
IMPLEMENTATION_HASH = _file_hash(Path(__file__))
HAZARD = list(POLICY['hazard_weights'])
EXPOSURE = ['food_contact', 'human_biomonitoring', 'inventory', 'production', 'patent', 'literature']
FINAL_FIELDS = ['Hazard_score', 'Exposure_score', 'Priority_score', 'Hazard_data_status',
                'Exposure_data_status', 'Priority_data_status', 'Priority_tier']


def score_value(value, maximum=2):
    """Accept finite scores or explicit missing values; reject malformed inputs."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean values cannot be scores.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Malformed score: ' + str(value)) from exc
    if not result.is_finite() or not 0 <= result <= maximum:
        raise ValueError('Score outside its finite permitted range: ' + str(value))
    return result


def flag(value):
    if value is True or value == 'True':
        return True
    if value is False or value == 'False':
        return False
    raise ValueError('Availability must be an explicit boolean.')


def tier(hazard, exposure):
    """Classify numeric screening totals with the frozen dual gates."""
    h, e = score_value(hazard, 16), score_value(exposure, 10)
    if h is None or e is None:
        return POLICY['rules']['incomplete_tier']
    for label in ['High priority', 'Moderate priority']:
        gates = POLICY['tiers'][label]
        if h + e >= gates['total'] and h >= gates['hazard'] and e >= gates['exposure']:
            return label
    return 'Low priority'


def historical_scores(row):
    """Reproduce frozen Step 21 under its complete-column input contract."""
    values = [score_value(row[c]) for c in HAZARD]
    components = [score_value(row['Exposure_' + c + '_score']) for c in EXPOSURE]
    e = score_value(row['Exposure_score'], 10)
    if e is None or any(v is None for v in components) or sum(components) != e:
        raise ValueError('Historical exposure contract is incomplete or inconsistent.')
    h = sum((v if v is not None else Decimal(0)) * POLICY['hazard_weights'][c]
            for c, v in zip(HAZARD, values))
    return {'Hazard_score': float(h), 'Exposure_score': float(e), 'Priority_score': float(h + e),
            'Hazard_data_status': 'Has data' if any(v is not None for v in values) else 'No data',
            'Exposure_data_status': 'Has data', 'Priority_data_status': 'Has data',
            'Priority_tier': tier(h, e)}


def analysis_scores(row):
    """Missing evidence contributes zero only to sums; input scores remain missing."""
    hazard = {c: score_value(row[c]) for c in HAZARD}
    for c, value in hazard.items():
        stem = c.removesuffix('_score').lower()
        if flag(row[stem + '_available']) != (value is not None):
            raise ValueError('Hazard availability contradicts the component score: ' + c)
        if value is None and not row[stem + '_unavailable_reason']:
            raise ValueError('Missing hazard component has no explanation: ' + c)
    exposure = {c: score_value(row['Exposure_' + c + '_score']) for c in EXPOSURE}
    for c, value in exposure.items():
        if flag(row['exposure_' + c + '_available']) != (value is not None):
            raise ValueError('Exposure availability contradicts the component score: ' + c)
        if value is None and not row['exposure_' + c + '_unavailable_reason']:
            raise ValueError('Missing exposure component has no explanation: ' + c)
    missing_h = [c.removesuffix('_score') for c, v in hazard.items() if v is None]
    missing_e = [c for c, v in exposure.items() if v is None]
    e_complete = not missing_e
    e = score_value(row['Exposure_score'], 10)
    if flag(row['Exposure_complete']) != e_complete:
        raise ValueError('Exposure completeness contradicts available components or total.')
    e_observed = sum(v for v in exposure.values() if v is not None)
    if e != e_observed:
        raise ValueError('Exposure total differs from its available component sum.')
    h_observed = sum(v * POLICY['hazard_weights'][c] for c, v in hazard.items() if v is not None)
    h = h_observed
    eligible = any(v is not None for v in [*hazard.values(), *exposure.values()])
    reasons = ([{'domain': 'hazard', 'dimension': c, 'reason': row[c.lower() + '_unavailable_reason']}
                for c in missing_h] +
               [{'domain': 'exposure', 'dimension': c, 'reason': row['exposure_' + c + '_unavailable_reason']}
                for c in missing_e])
    def status(values):
        count = sum(v is not None for v in values)
        return 'Complete' if count == len(values) else 'Partial' if count else 'Unavailable'
    return {'Hazard_score': float(h) if h is not None else None,
            'Hazard_observed_score': float(h_observed), 'Hazard_complete': not missing_h,
            'Hazard_available_dimensions': 4 - len(missing_h), 'Hazard_missing_dimensions': _json(missing_h),
            'Hazard_data_status': status(list(hazard.values())),
            'Exposure_data_status': status(list(exposure.values())),
            'Priority_score': float(h + e) if eligible else None,
            'Priority_eligible': eligible, 'Priority_tier': tier(h, e) if eligible else 'No data',
            'Priority_data_status': 'Complete' if not missing_h and e_complete else 'Partial' if eligible else 'No data',
            'Priority_missing_reasons': _json(reasons),
            'Priority_ineligibility_reasons': _json([] if eligible else [{'domain': 'assessment', 'dimension': 'all', 'reason': 'no_available_hazard_or_exposure_evidence'}]),
            'priority_scoring_policy': POLICY['policy_version'],
            'priority_result_role': 'analysis_after_eligibility_audit'}


def keyed(frame, keys):
    if frame['inchikey'].eq('').any() or frame['inchikey'].duplicated().any() or set(frame['inchikey']) != set(keys):
        raise ValueError('Compound identities are empty, duplicated or inconsistent.')
    return frame.set_index('inchikey').loc[keys].reset_index()


def unchanged(a, b, numeric=False):
    if numeric:
        return score_value(a, 26) == score_value(b, 26)
    return a == b


def change_reasons(old_inputs, row, calculated, field):
    reasons = []
    if field.endswith('data_status'):
        reasons.append('availability_status_distinguishes_complete_partial_and_unavailable')
    if not field.startswith('Exposure') and any(not unchanged(old_inputs[c], row[c], True) for c in HAZARD):
        reasons.append('upstream_hazard_identity_isolation')
    if not field.startswith('Hazard') and any(not unchanged(old_inputs['Exposure_' + c + '_score'], row['Exposure_' + c + '_score'], True) for c in EXPOSURE):
        reasons.append('upstream_exposure_eligibility_audit')
    if not calculated['Priority_eligible'] and field.startswith('Priority'):
        reasons.append('no_available_hazard_or_exposure_evidence')
    return reasons


@dataclass
class PriorityResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    summary: pd.DataFrame
    changes: pd.DataFrame
    decisions: list
    manifest: dict
    upstream: Path

    def write_reports(self, output_dir):
        out = Path(output_dir).resolve()
        root = self.upstream.parent.parent
        protected = [root / ('stage' + str(i)) for i in range(2, 7)]
        protected.append(Path(__file__).resolve().parent.parent / 'data')
        if out == root or any(out == p or out.is_relative_to(p) or p.is_relative_to(out) for p in protected):
            raise ValueError('Stage 7A output must not overwrite upstream results or input data.')
        out.mkdir(parents=True, exist_ok=True)
        (out / 'priority_manifest.json').unlink(missing_ok=True)
        for name, frame in [('compound_priority_assessment', self.compounds), ('priority_historical', self.historical),
                            ('priority_summary', self.summary), ('priority_changes', self.changes)]:
            frame.to_csv(out / (name + '.csv'), index=False, encoding='utf-8', lineterminator='\n')
        with (out / 'priority_decisions.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
            for record in self.decisions:
                stream.write(_json(record) + '\n')
        shutil.copyfile(self.upstream / 'identity_review_source_links.jsonl', out / 'identity_review_source_links.jsonl')
        names = ['compound_priority_assessment.csv', 'priority_historical.csv', 'priority_summary.csv',
                 'priority_changes.csv', 'priority_decisions.jsonl', 'identity_review_source_links.jsonl']
        self.manifest['output_sha256'] = {name: _file_hash(out / name) for name in names}
        (out / 'priority_manifest.json').write_text(json.dumps(self.manifest, indent=2) + '\n', encoding='utf-8')


def integrate_priority(exposure_results):
    upstream = Path(exposure_results).resolve()
    root = upstream.parent.parent
    paths = {'exposure': upstream / 'exposure_scoring_manifest.json',
             'bt': root / 'stage5' / '5b' / 'bt_manifest.json', 'pm': root / 'stage5' / 'hazard_manifest.json'}
    hashes = {k: _file_hash(p) for k, p in paths.items()}
    manifests = {k: json.loads(p.read_text(encoding='utf-8')) for k, p in paths.items()}
    for k, path in paths.items():
        _verify_outputs(path.parent, manifests[k])
    if (manifests['exposure']['upstream_manifests_sha256']['bt'] != hashes['bt'] or
            manifests['bt']['upstream_manifests_sha256']['pm'] != hashes['pm']):
        raise ValueError('Priority inputs refer to different upstream runs.')
    def verify_code():
        if POLICY['schema_version'] != 1 or _file_hash(POLICY_PATH) != POLICY_HASH or _file_hash(Path(__file__)) != IMPLEMENTATION_HASH:
            raise ValueError('Priority policy or implementation changed; restart the process.')
        for name, filename, policy in [('exposure', 'exposure.py', 'exposure_policy.json'),
                                        ('bt', 'hazard_bt.py', 'hazard_bt_policy.json'),
                                        ('pm', 'hazard.py', 'hazard_policy.json')]:
            for file, field in [(filename, 'implementation_sha256'), (policy, 'policy_sha256')]:
                if _file_hash(Path(__file__).with_name(file)) != manifests[name][field]:
                    raise ValueError('Upstream implementation or policy changed: ' + file)
    verify_code()
    compounds = _read_csv(upstream / 'compound_exposure_scores.csv')
    require_prediction_isolation(compounds)
    keys = compounds['inchikey'].tolist()
    keyed(compounds, keys)
    if not compounds['exposure_result_role'].eq('analysis_after_eligibility_audit').all():
        raise ValueError('Stage 7A requires the audited exposure analysis view.')
    history = pd.DataFrame({'inchikey': keys})
    for folder, file, columns in [(paths['pm'].parent, 'pm_historical.csv', HAZARD[:2]),
                                  (paths['bt'].parent, 'bt_historical.csv', HAZARD[2:]),
                                  (upstream, 'exposure_historical.csv', ['Exposure_score'] + ['Exposure_' + c + '_score' for c in EXPOSURE])]:
        source = keyed(_read_csv(folder / file), keys)
        if not source['result_role'].eq('historical_reproduction_only').all():
            raise ValueError('Expected explicitly labelled historical inputs.')
        for column in columns:
            history[column] = source[column]
    historic_rows, analysis_rows, decisions, changes = [], [], [], []
    for old, row in zip(history.to_dict('records'), compounds.to_dict('records')):
        h = historical_scores(old)
        a = analysis_scores(row)
        historic_rows.append({**old, **h, 'result_role': 'historical_reproduction_only'})
        analysis_rows.append(a)
        components = {c: {'historical_score': old[c], 'analysis_score': row[c],
                         'weight': POLICY['hazard_weights'][c],
                         'unavailable_reason': row[c.removesuffix('_score').lower() + '_unavailable_reason']}
                      for c in HAZARD}
        evidence_links = {'pm': 'pm_decisions.jsonl', 'bt': 'bt_decisions.jsonl',
                          'exposure': 'exposure_analysis_decisions.jsonl'}
        decisions.append({'inchikey': row['inchikey'], 'historical': h, 'analysis': a,
                          'hazard_components': components,
                          'exposure_components': {c: {'historical_score': old['Exposure_' + c + '_score'],
                                                     'analysis_score': row['Exposure_' + c + '_score'],
                                                     'unavailable_reason': row['exposure_' + c + '_unavailable_reason']}
                                                  for c in EXPOSURE},
                          'qsar_identity_status': row['qsar_identity_status'], 'qsar_identity_reason': row['qsar_identity_reason'],
                          'gic_context': {c: row[c] for c in row if c.startswith(('gic_', 'GIC_'))},
                          'source_decision_files': evidence_links, 'source_join_key': row['inchikey'],
                          'upstream_manifests_sha256': hashes})
        for field in FINAL_FIELDS:
            after = row['Exposure_score'] if field == 'Exposure_score' else a[field]
            if not unchanged(h[field], after, field.endswith('_score')):
                changes.append({'inchikey': row['inchikey'], 'field': field,
                                'historical_value': _json(h[field]), 'analysis_value': _json(after if after != '' else None),
                                'change_reasons': _json(change_reasons(old, row, a, field)),
                                'missing_reasons': a['Priority_missing_reasons'],
                                'qsar_identity_status': row['qsar_identity_status']})
    analysis = compounds.copy()
    for c in analysis_rows[0]:
        if c in analysis.columns:
            raise ValueError('Stage 7A must not replace an upstream field: ' + c)
        analysis[c] = [r[c] for r in analysis_rows]
    historical = pd.DataFrame(historic_rows)
    summary = []
    for role, frame in [('historical_reproduction_only', historical), ('analysis_after_eligibility_audit', analysis)]:
        for field in ['Hazard_data_status', 'Exposure_data_status', 'Priority_data_status', 'Priority_tier']:
            for value, count in sorted(frame[field].value_counts(dropna=False).items()):
                summary.append({'result_role': role, 'field': field, 'value': value, 'compounds': int(count)})
    require_prediction_isolation(analysis)
    verify_code()
    for k, path in paths.items():
        if _file_hash(path) != hashes[k]:
            raise ValueError('Upstream manifest changed during priority assessment.')
        _verify_outputs(path.parent, manifests[k])
    counts = {'compounds': len(analysis), 'historical_fields': len(FINAL_FIELDS),
              'complete_hazard': int(analysis['Hazard_complete'].sum()),
              'eligible_priority': int(analysis['Priority_eligible'].sum()),
              'ineligible_priority': int((~analysis['Priority_eligible']).sum()),
              'identity_review_compounds': int(analysis['qsar_identity_status'].eq('review_required').sum()),
              'field_changes': len(changes)}
    manifest = {'schema_version': 1, 'stage': '7A', 'policy_sha256': POLICY_HASH,
                'implementation_sha256': IMPLEMENTATION_HASH, 'upstream_manifests_sha256': hashes,
                'counts': counts, 'rules': POLICY['rules'], 'ranking_computed': False,
                'runtime': {'python': platform.python_version(), 'pandas': pd.__version__}}
    return PriorityResult(analysis, historical, pd.DataFrame(summary),
                          pd.DataFrame(changes, columns=['inchikey', 'field', 'historical_value', 'analysis_value',
                                                        'change_reasons', 'missing_reasons', 'qsar_identity_status']),
                          decisions, manifest, upstream)
