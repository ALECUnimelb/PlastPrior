"""Pure scenario scoring over frozen, unweighted component scores.

This module never mutates source records or writes to the formal evidence archive.
Label thresholds and scale choices are explicit: no scientific defaults are inferred.
"""
from decimal import Decimal, InvalidOperation


HAZARD_WEIGHTS = {
    'Persistence_score': 2, 'Mobility_score': 1,
    'Bioaccumulation_score': 2, 'Toxicity_score': 3,
}
EXPOSURE_WEIGHTS = {
    'Exposure_food_contact_score': 1, 'Exposure_human_biomonitoring_score': 1,
    'Exposure_inventory_score': 3, 'Exposure_production_score': 1,
    'Exposure_patent_score': 2, 'Exposure_literature_score': 1,
}
COMPONENT_MAXIMA = {field: 2 for field in (*HAZARD_WEIGHTS, *EXPOSURE_WEIGHTS)}
COMPONENT_MAXIMA.update(Exposure_food_contact_score=1, Exposure_human_biomonitoring_score=1)
LABELS = ('L', 'M', 'H', 'vH')


def number(value):
    """Reject malformed, negative, nonfinite and boolean numeric inputs."""
    if isinstance(value, bool):
        raise ValueError('Boolean values are not scores or weights.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Expected a nonnegative finite number.') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Expected a nonnegative finite number.')
    return result


def weighted_domain(record, weights, domain, *, normalize_to):
    """Return raw and scaled contributions; missingness never changes the denominator.

All original score columns are required, including explicitly empty fields.
Zero-weight fields remain visible in the source missingness report.
"""
    fields = HAZARD_WEIGHTS if domain == 'hazard' else EXPOSURE_WEIGHTS if domain == 'exposure' else None
    if fields is None or set(weights) != set(fields):
        raise ValueError('Weights must contain exactly the component fields for the domain.')
    missing_columns = set(fields) - record.keys()
    if missing_columns:
        raise ValueError('Missing base score columns: ' + ', '.join(sorted(missing_columns)))
    parsed_weights = {field: number(value) for field, value in weights.items()}
    maximum = sum(parsed_weights[field] * COMPONENT_MAXIMA[field] for field in fields)
    if maximum == 0:
        raise ValueError('At least one domain weight must be positive.')
    target = maximum if normalize_to is None else number(normalize_to)
    if target == 0:
        raise ValueError('Normalized maximum must be positive.')
    scores = {}
    for field in fields:
        value = record[field]
        value = None if value is None or (isinstance(value, str) and not value.strip()) else number(value)
        if value is not None and value > COMPONENT_MAXIMA[field]:
            raise ValueError('Base component score outside its range: ' + field)
        scores[field] = value
    contributions = {field: (value if value is not None else Decimal(0)) * parsed_weights[field]
                     for field, value in scores.items()}
    raw = sum(contributions.values())
    # Multiply before dividing to avoid early recurring-decimal rounding.
    return {'score': raw * target / maximum, 'raw_score': raw,
            'maximum': target, 'raw_maximum': maximum,
            'contributions': {field: value * target / maximum for field, value in contributions.items()},
            'raw_contributions': contributions,
            'missing_fields': [field for field, value in scores.items() if value is None],
            'has_active_evidence': any(value is not None and parsed_weights[field] > 0
                                       for field, value in scores.items()),
            'complete': all(value is not None for value in scores.values())}


def domain_label(score, thresholds, *, upper_inclusive):
    """Three ascending cutpoints; upper_inclusive means a cutpoint enters the higher band."""
    if not isinstance(upper_inclusive, bool):
        raise ValueError('Cutpoint inclusivity must be explicit.')
    if not isinstance(thresholds, (list, tuple)) or len(thresholds) != 3:
        raise ValueError('Exactly three label cutpoints are required.')
    cuts = [number(value) for value in thresholds]
    if not (0 < cuts[0] < cuts[1] < cuts[2]):
        raise ValueError('Label cutpoints must be positive and strictly increasing.')
    value = number(score)
    return LABELS[sum(value >= cut if upper_inclusive else value > cut for cut in cuts)]


def priority_level(hazard_label, exposure_label):
    """The approved symmetric 4x4 decision matrix; unknown domains stay unclassified."""
    if hazard_label is None or exposure_label is None:
        return None
    if hazard_label not in LABELS or exposure_label not in LABELS:
        raise ValueError('Unknown domain label.')
    low, high = sorted((LABELS.index(hazard_label), LABELS.index(exposure_label)))
    if high == 3 and low >= 2:
        return 1
    if high == 3 or low == 2:
        return 2
    if high == 2:
        return 3
    return 4


def default_policy():
    import json
    from pathlib import Path
    return json.loads(Path(__file__).with_name('scenario_policy.json').read_text())


def validate_policy(policy):
    expected = default_policy()
    if set(policy) != set(expected):
        raise ValueError('Scenario configuration has missing or unknown fields.')
    for field in ['schema_version', 'policy_version', 'rounding', 'normalization', 'ranking', 'missingness']:
        if policy[field] != expected[field]:
            raise ValueError('Unsupported scenario policy: ' + field)
    if isinstance(policy['top_n'], bool) or not isinstance(policy['top_n'], int) or policy['top_n'] < 1:
        raise ValueError('Top-N must be a positive integer.')
    if set(policy['thresholds']) != {'hazard', 'exposure'}:
        raise ValueError('Both domain thresholds are required.')
    for domain in ['hazard', 'exposure']:
        weights = policy[domain + '_weights']
        import re
        for value in weights.values():
            if not re.fullmatch(r'\d+(?:\.\d{1,6})?', str(value)) or number(value) > 100:
                raise ValueError('Weights must be between 0 and 100 with at most six decimal places.')
        for value in policy['thresholds'][domain]:
            if not re.fullmatch(r'\d+(?:\.\d{1,6})?', str(value)):
                raise ValueError('Cutpoints require at most six decimal places.')
        weighted_domain(COMPONENT_MAXIMA, weights, domain, normalize_to=None)
        domain_label(0, policy['thresholds'][domain], upper_inclusive=True)


def score_record(record, policy):
    """Caller validates policy once per population; no intermediate rounding."""
    from decimal import ROUND_HALF_UP
    import json
    results = {d: weighted_domain(record, policy[d + '_weights'], d, normalize_to=None)
               for d in ['hazard', 'exposure']}
    eligible = any(r['has_active_evidence'] for r in results.values())
    output = {}
    for domain, result in results.items():
        name = domain.capitalize()
        rounded = int(result['score'].quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        output.update({name + '_score_raw': str(result['score']), name + '_score': rounded,
                       name + '_score_max': str(result['maximum']), name + '_observed_score': str(result['score']),
                       name + '_label': domain_label(rounded, policy['thresholds'][domain], upper_inclusive=True) if eligible else '',
                       name + '_weighted_contributions': json.dumps({k: str(v) for k, v in result['raw_contributions'].items()}, sort_keys=True)})
    level = priority_level(output['Hazard_label'], output['Exposure_label']) if eligible else None
    output.update(Priority_score=output['Hazard_score'] + output['Exposure_score'] if eligible else None,
                  Priority_level=level, Priority_tier=f'Level {level}' if level else 'No data',
                  Priority_eligible=eligible, Ranking_eligible=eligible,
                  Priority_data_status=('Complete' if all(r['complete'] for r in results.values()) else 'Partial') if eligible else 'No data',
                  Priority_ineligibility_reasons='[]' if eligible else '[{"reason":"no_active_weighted_evidence"}]',
                  Ranking_exclusion_reasons='[]' if eligible else '[{"reason":"no_active_weighted_evidence"}]',
                  priority_scoring_policy=policy['policy_version'],
                  scoring_config_json=json.dumps(policy, sort_keys=True, separators=(',', ':')))
    return output


def score_population(records, policy):
    from collections import Counter
    validate_policy(policy)
    keys = [str(r.get('inchikey', '')).strip() for r in records]
    if not records or '' in keys or len(set(keys)) != len(keys):
        raise ValueError('A nonempty population with unique inchikey values is required.')
    rows = [{**record, **score_record(record, policy)} for record in records]
    counts = Counter(r['Priority_score'] for r in rows if r['Ranking_eligible'])
    ranks, seen = {}, 0
    for score in sorted(counts, reverse=True):
        ranks[score] = seen + 1
        seen += counts[score]
    for row in rows:
        score = row['Priority_score']
        rank = ranks.get(score)
        row.update(Priority_rank=rank, Priority_tie_size=counts.get(score) if rank else None,
                   Top_n_selected=rank <= policy['top_n'] if rank else None)
    return sorted(rows, key=lambda r: (r['Priority_rank'] or float('inf'), r['inchikey']))
