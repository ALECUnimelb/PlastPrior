"""Stage 7B: eligible competition ranks, inclusive Top-N and historical order."""
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
import shutil

import numpy as np
import pandas as pd

from .evidence import _json, _read_csv
from .evidence_specialists import require_prediction_isolation
from .inputs import _file_hash
from .lrtp import _verify_outputs
from .priority import analysis_scores, flag, score_value

POLICY_PATH = Path(__file__).with_name('ranking_policy.json')
POLICY_HASH = _file_hash(POLICY_PATH)
POLICY = json.loads(POLICY_PATH.read_text(encoding='utf-8'))
IMPLEMENTATION_HASH = _file_hash(Path(__file__))


def valid_n(n):
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError('Top-N must be a positive integer.')


def rank_scores(scores):
    """Return competition rank and group size for exact finite scores."""
    counts = Counter(scores.values())
    ranks, seen = {}, 0
    for value in sorted(counts, reverse=True):
        ranks[value] = seen + 1
        seen += counts[value]
    return {key: (ranks[value], counts[value]) for key, value in scores.items()}


def eligible_ranking(frame, top_n):
    """Rank an already qualified table; canonical output is independent of input order."""
    valid_n(top_n)
    if frame['inchikey'].eq('').any() or frame['inchikey'].duplicated().any():
        raise ValueError('Ranking requires unique nonempty full InChIKeys.')
    scores = {}
    for row in frame.to_dict('records'):
        value = score_value(row['Priority_score'], 26)
        eligible = flag(row['Priority_eligible'])
        if eligible != (value is not None):
            raise ValueError('Priority score and qualification disagree.')
        if eligible:
            scores[row['inchikey']] = value
    ranks = rank_scores(scores)
    order = sorted(scores, key=lambda key: (-scores[key], key))
    cutoff = scores[order[min(top_n, len(order)) - 1]] if order else None
    rows = []
    for key in sorted(frame['inchikey']):
        eligible = key in scores
        rows.append({'inchikey': key, 'Ranking_eligible': eligible,
                     'Priority_rank': ranks[key][0] if eligible else None,
                     'Priority_tie_size': ranks[key][1] if eligible else None,
                     'Top_n_selected': scores[key] >= cutoff if eligible else None})
    result = pd.DataFrame(rows, columns=['inchikey', 'Ranking_eligible', 'Priority_rank', 'Priority_tie_size', 'Top_n_selected'])
    for c in ['Priority_rank', 'Priority_tie_size']:
        result[c] = pd.array(result[c], dtype='Int64')
    result['Top_n_selected'] = pd.array(result['Top_n_selected'], dtype='boolean')
    summary = {'requested_n': top_n, 'eligible_compounds': len(scores),
               'selected_compounds': sum(v >= cutoff for v in scores.values()) if scores else 0,
               'cutoff_score': float(cutoff) if cutoff is not None else None,
               'boundary_tie_size': sum(v == cutoff for v in scores.values()) if scores else 0,
               'top_n_exceeds_pool': top_n > len(scores)}
    return result, order, summary


def historical_order(frame):
    """Retain frozen input order before the legacy single-column sort."""
    digest = hashlib.sha256(('\n'.join(frame['inchikey']) + '\n').encode('utf-8')).hexdigest()
    if digest != POLICY['historical']['input_order_sha256']:
        raise ValueError('Historical input order differs from the frozen run.')
    scores = {r['inchikey']: score_value(r['Priority_score'], 26) for r in frame.to_dict('records')}
    if any(v is None for v in scores.values()):
        raise ValueError('Historical priority scores must be complete.')
    result = frame.copy()
    result['_sort_score'] = pd.to_numeric(result['Priority_score'], errors='raise')
    result = result.sort_values('_sort_score', ascending=False, na_position='last', kind='quicksort').drop(columns='_sort_score').reset_index(drop=True)
    top_digest = hashlib.sha256(('\n'.join(result.head(100)['inchikey']) + '\n').encode('utf-8')).hexdigest()
    if top_digest != POLICY['historical']['top100_order_sha256']:
        raise ValueError('Historical Top-100 order differs from its frozen fingerprint. Use the recorded pandas/NumPy environment and rerun validation; do not substitute a new tie order.')
    result['Historical_sort_position'] = range(1, len(result) + 1)
    ranks = rank_scores(scores)
    result['Historical_derived_score_rank'] = [ranks[k][0] for k in result['inchikey']]
    result['Historical_tie_size'] = [ranks[k][1] for k in result['inchikey']]
    return result


@dataclass
class RankingResult:
    tables: dict
    summary: dict
    manifest: dict
    upstream: Path

    def write_reports(self, output_dir):
        out = Path(output_dir).resolve()
        root = self.upstream.parent.parent
        protected = [root / ('stage' + str(i)) for i in range(2, 7)] + [self.upstream, Path(__file__).resolve().parent.parent / 'data']
        if any(out == p or out.is_relative_to(p) or p.is_relative_to(out) for p in protected):
            raise ValueError('Stage 7B must not overwrite input data or upstream results.')
        out.mkdir(parents=True, exist_ok=True)
        (out / 'ranking_manifest.json').unlink(missing_ok=True)
        names = []
        for name, table in self.tables.items():
            filename = name + '.csv'
            table.to_csv(out / filename, index=False, encoding='utf-8', lineterminator='\n')
            names.append(filename)
        (out / 'ranking_summary.json').write_text(json.dumps(self.summary, indent=2) + '\n', encoding='utf-8')
        names.append('ranking_summary.json')
        shutil.copyfile(self.upstream / 'identity_review_source_links.jsonl', out / 'identity_review_source_links.jsonl')
        names.append('identity_review_source_links.jsonl')
        self.manifest['output_sha256'] = {name: _file_hash(out / name) for name in names}
        (out / 'ranking_manifest.json').write_text(json.dumps(self.manifest, indent=2) + '\n', encoding='utf-8')


def integrate_ranking(priority_results, top_n=100):
    valid_n(top_n)
    upstream = Path(priority_results).resolve()
    path = upstream / 'priority_manifest.json'
    fingerprint = _file_hash(path)
    parent = json.loads(path.read_text(encoding='utf-8'))
    _verify_outputs(upstream, parent)
    def verify_code():
        for file, digest in [(POLICY_PATH, POLICY_HASH), (Path(__file__), IMPLEMENTATION_HASH),
                             (Path(__file__).with_name('priority.py'), parent['implementation_sha256']),
                             (Path(__file__).with_name('priority_policy.json'), parent['policy_sha256'])]:
            if _file_hash(file) != digest:
                raise ValueError('Ranking or upstream implementation/policy changed: ' + file.name)
        if POLICY['schema_version'] != 1 or parent['stage'] != '7A' or parent['ranking_computed'] is not False:
            raise ValueError('Expected verified Stage 7A assessments.')
    verify_code()
    compounds = _read_csv(upstream / 'compound_priority_assessment.csv')
    history = _read_csv(upstream / 'priority_historical.csv')
    require_prediction_isolation(compounds)
    if (history['inchikey'].duplicated().any() or set(history['inchikey']) != set(compounds['inchikey']) or
            not history['result_role'].eq('historical_reproduction_only').all()):
        raise ValueError('Historical and analysis identities or roles differ.')
    for row in compounds.to_dict('records'):
        expected = analysis_scores(row)
        for c in ['Priority_eligible', 'Priority_tier', 'Priority_data_status', 'priority_result_role', 'Priority_ineligibility_reasons']:
            if str(expected[c]) != row[c]:
                raise ValueError('Stage 7A qualification is inconsistent: ' + c)
        if score_value(row['Priority_score'], 26) != score_value(expected['Priority_score'], 26):
            raise ValueError('Stage 7A aggregate is inconsistent.')
    ranks, order, summary = eligible_ranking(compounds, top_n)
    all_records = compounds.set_index('inchikey').loc[ranks['inchikey']].reset_index()
    for c in ranks.columns[1:]:
        all_records[c] = ranks[c].array
    all_records['Ranking_exclusion_reasons'] = all_records['Priority_ineligibility_reasons']
    all_records['ranking_result_role'] = 'analysis_rank_within_complete_evidence_pool'
    compact = ['inchikey', 'name_resolved', 'cas_reported', 'representative_record_id', 'source_tables_json',
               'Persistence_score', 'Mobility_score', 'Bioaccumulation_score', 'Toxicity_score',
               'Hazard_score', 'Exposure_score', 'Priority_score', 'Priority_tier', 'Priority_eligible',
               'Hazard_available_dimensions', 'Exposure_available_dimensions', 'Hazard_missing_dimensions',
               'Exposure_missing_dimensions', 'Priority_ineligibility_reasons', 'qsar_identity_status', 'qsar_identity_reason',
               'Priority_rank', 'Priority_tie_size', 'Top_n_selected', 'Ranking_eligible', 'Ranking_exclusion_reasons', 'ranking_result_role']
    compact += [c for c in all_records if c.startswith(('gic_', 'GIC_'))]
    compact = [c for c in compact if c in all_records]
    ranked = all_records.set_index('inchikey').loc[order].reset_index()[compact]
    top = ranked.loc[ranked['Top_n_selected'].fillna(False)].copy()
    unranked = all_records.loc[~all_records['Ranking_eligible'], compact].copy()
    historical = historical_order(history)
    old_positions = dict(zip(historical['inchikey'], historical['Historical_sort_position']))
    display_positions = {key: i + 1 for i, key in enumerate(order)}
    old_scores = {r['inchikey']: score_value(r['Priority_score'], 26) for r in history.to_dict('records')}
    old_ranks = rank_scores(old_scores)
    eligible_old_ranks = rank_scores({k: old_scores[k] for k in order})
    old_top = set(historical.head(top_n)['inchikey'])
    old_top100 = set(historical.head(100)['inchikey'])
    old_cutoff = old_scores[historical.iloc[min(top_n, len(historical)) - 1]['inchikey']]
    old_inclusive = {k for k, v in old_scores.items() if v >= old_cutoff}
    current = set(top['inchikey'])
    membership = []
    for row in all_records.to_dict('records'):
        key = row['inchikey']
        eligible = bool(row['Ranking_eligible'])
        new_score = score_value(row['Priority_score'], 26)
        r0 = old_ranks[key][0]
        r1 = eligible_old_ranks[key][0] if eligible else None
        r2 = int(row['Priority_rank']) if eligible else None
        reasons = []
        if not eligible:
            reasons.append('ineligible_incomplete_evidence')
        else:
            if r1 != r0:
                reasons.append('ranking_pool_changed_by_eligibility')
            if new_score != old_scores[key]:
                reasons.append('own_priority_score_changed_upstream')
            if r2 != r1:
                reasons.append('relative_order_changed_by_score_updates_within_eligible_pool')
            if int(row['Priority_tie_size']) > 1:
                reasons.append('tied_group_displayed_by_identifier_without_breaking_rank_tie')
        if key in old_inclusive and key not in old_top:
            reasons.append('historical_strict_top_n_truncated_boundary_tie')
        if (key in old_top) != (key in current):
            reasons.append('top_n_membership_changed')
        if not reasons:
            reasons.append('unchanged_competition_rank_and_membership')
        membership.append({'inchikey': key, 'requested_n': top_n, 'historical_top100_member': key in old_top100,
                           'historical_strict_top_n_member': key in old_top, 'analysis_top_n_member': key in current if eligible else None,
                           'historical_score': float(old_scores[key]), 'analysis_score': float(new_score) if eligible else None,
                           'historical_sort_position': old_positions[key],
                           'analysis_display_position': display_positions.get(key),
                           'historical_derived_rank': r0, 'historical_rank_in_current_eligible_pool': r1,
                           'analysis_rank': r2, 'eligibility_pool_rank_shift': r1 - r0 if eligible else None,
                           'score_update_rank_shift': r2 - r1 if eligible else None,
                           'change_reasons': _json(reasons), 'ineligibility_reasons': row['Priority_ineligibility_reasons'],
                           'source_decision_file': 'priority_decisions.jsonl', 'source_join_key': key,
                           'upstream_manifest_sha256': fingerprint})
    audit = pd.DataFrame(membership)
    for c in ['historical_sort_position', 'analysis_display_position', 'historical_derived_rank', 'historical_rank_in_current_eligible_pool', 'analysis_rank', 'eligibility_pool_rank_shift', 'score_update_rank_shift']:
        audit[c] = pd.array(audit[c], dtype='Int64')
    audit['analysis_top_n_member'] = pd.array(audit['analysis_top_n_member'], dtype='boolean')
    summary.update({'compounds': len(compounds), 'unranked_compounds': len(unranked),
                    'identity_review_compounds': int(compounds['qsar_identity_status'].eq('review_required').sum()),
                    'historical_top100_count': min(100, len(historical)),
                    'historical_comparison': 'Legacy ordinal positions are distinct from newly derived competition ranks.',
                    'top_n_membership_entered': len(current - old_top), 'top_n_membership_left': len(old_top - current)})
    tables = {'compound_rankings': all_records, 'eligible_priority_ranking': ranked,
              'top_priority_including_ties': top, 'unranked_review': unranked,
              'historical_priority_order': historical, 'historical_top100': historical.head(100).copy(),
              'ranking_changes': audit}
    verify_code()
    if _file_hash(path) != fingerprint:
        raise ValueError('Upstream manifest changed during ranking.')
    _verify_outputs(upstream, parent)
    manifest = {'schema_version': 1, 'stage': '7B', 'policy_sha256': POLICY_HASH,
                'implementation_sha256': IMPLEMENTATION_HASH, 'upstream_manifest_sha256': fingerprint,
                'top_n': top_n, 'rules': POLICY['rules'], 'counts': summary,
                'historical_environment_matches': pd.__version__ == POLICY['historical']['environment']['pandas'] and np.__version__ == POLICY['historical']['environment']['numpy'],
                'runtime': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__}}
    return RankingResult(tables, summary, manifest, upstream)
