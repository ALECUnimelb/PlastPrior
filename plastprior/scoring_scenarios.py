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
