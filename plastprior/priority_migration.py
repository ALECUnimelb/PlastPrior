"""Strict, independently calculated audit of the approved classification-only migration."""
import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .inputs import _file_hash

OLD_POLICY = 'priority-zero-contribution-v1'
NEW_POLICY = 'priority-hgt10-ege5-v1'
ALLOWED_FIELDS = {'Priority_tier', 'priority_scoring_policy'}
REQUIRED = {'inchikey', 'Hazard_score', 'Exposure_score', 'Priority_score',
            'Priority_tier', 'Priority_data_status', 'priority_scoring_policy',
            'Ranking_eligible', 'Priority_rank', 'Priority_tie_size', 'Top_n_selected'}


def _read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or not REQUIRED <= set(fields):
            raise ValueError('Migration requires the complete scored publication schema.')
        rows = list(reader)
    indexed = {row['inchikey']: row for row in rows}
    if not rows or '' in indexed or len(rows) != len(indexed):
        raise ValueError('Empty or duplicate compound identities in migration.')
    return fields, indexed


def _expected(row, new):
    h, e = Decimal(row['Hazard_score']), Decimal(row['Exposure_score'])
    if not h.is_finite() or not e.is_finite() or not (0 <= h <= 16 and 0 <= e <= 10):
        raise ValueError('Invalid raw domain score in migration.')
    if row['Priority_data_status'] == 'No data':
        if row['Priority_score'] or row['Ranking_eligible'] != 'False':
            raise ValueError('No-data row must remain unranked without a total.')
        return 'No data'
    if Decimal(row['Priority_score']) != h + e or row['Ranking_eligible'] != 'True':
        raise ValueError('Raw aggregate or ranking eligibility disagrees.')
    if new:
        # Independent literal inequalities, not the production classifier or plotting bins.
        if h > 10:
            return 'High priority' if e >= 5 else 'Moderate priority'
        return 'Moderate priority' if h >= 6 and e >= 5 else 'Low priority'
    if h + e >= 12 and h >= 4 and e >= 4:
        return 'High priority'
    return 'Moderate priority' if h + e >= 6 and h >= 2 and e >= 2 else 'Low priority'


def verify_priority_migration(baseline, candidate):
    """Allow only verified old-to-new tiers and their version; all other lexemes must match."""
    baseline, candidate = Path(baseline).resolve(), Path(candidate).resolve()
    if baseline == candidate:
        raise ValueError('Migration requires separate old and new files.')
    fields, old = _read(baseline)
    new_fields, new = _read(candidate)
    if fields != new_fields or old.keys() != new.keys():
        raise ValueError('Publication schema or compound universe changed.')
    invariant = [f for f in fields if f not in ALLOWED_FIELDS]
    transitions, old_counts, new_counts, changed = Counter(), Counter(), Counter(), Counter()
    for key, before in old.items():
        after = new[key]
        for field in invariant:
            if before[field] != after[field]:
                raise ValueError(f'Unexpected migration change: {key}:{field}')
        if before['priority_scoring_policy'] != OLD_POLICY or after['priority_scoring_policy'] != NEW_POLICY:
            raise ValueError('Unsupported policy migration.')
        if before['Priority_tier'] != _expected(before, False) or after['Priority_tier'] != _expected(after, True):
            raise ValueError(f'Independent classification mismatch: {key}')
        for field in ALLOWED_FIELDS:
            changed[field] += before[field] != after[field]
        old_counts[before['Priority_tier']] += 1
        new_counts[after['Priority_tier']] += 1
        transitions[(before['Priority_tier'], after['Priority_tier'])] += 1
    return {'status': 'passed', 'baseline_sha256': _file_hash(baseline),
            'candidate_sha256': _file_hash(candidate), 'rows': len(old),
            'old_policy': OLD_POLICY, 'new_policy': NEW_POLICY,
            'unchanged_fields': invariant, 'changed_field_counts': dict(changed),
            'old_tier_counts': dict(old_counts), 'new_tier_counts': dict(new_counts),
            'top_n_count': sum(r['Top_n_selected'] == 'True' for r in new.values()),
            'transitions': [{'old': a, 'new': b, 'n': n} for (a, b), n in sorted(transitions.items())]}
