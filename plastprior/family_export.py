"""Attach versioned structural annotations without changing scientific results."""
from collections import Counter
import json

from .chemical_families import CATEGORY_ORDER, RULE_DESCRIPTIONS, RULE_VERSION, classify_smiles, require_rdkit


def annotate_archive(db):
    require_rdkit()
    from rdkit import rdBase

    db.execute('''CREATE TABLE chemical_family_audit (
        inchikey TEXT PRIMARY KEY REFERENCES compounds(inchikey),
        category_labels TEXT NOT NULL, original_smiles TEXT NOT NULL,
        parent_smiles TEXT NOT NULL, classification_status TEXT NOT NULL,
        matched_rules TEXT NOT NULL, warning TEXT NOT NULL,
        is_salt INTEGER NOT NULL, parent_changed INTEGER NOT NULL,
        counterion_fragments TEXT NOT NULL, rule_version TEXT NOT NULL)''')
    counts, statuses, overlaps = Counter(), Counter(), Counter()
    total = categorized = 0
    for key, smiles in db.execute('SELECT inchikey,smiles_isomeric FROM compounds ORDER BY inchikey'):
        result = classify_smiles(smiles)
        labels = result['category_labels']
        status = result['status']
        if status in ('ok', 'ok_with_warning') and not labels:
            status = 'unclassified' if status == 'ok' else 'unclassified_with_warning'
        db.execute('INSERT INTO chemical_family_audit VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
            key, labels, smiles or '', result['parent_smiles'], status,
            result['matched_rules'], result['warning'], int(result['is_salt']),
            int(result['parent_changed']), result['counterion_fragments'], RULE_VERSION))
        total += 1
        categorized += bool(labels)
        members = [label.strip() for label in labels.split(';') if label.strip()]
        counts.update(members)
        statuses[status] += 1
        if len(members) > 1:
            overlaps[labels] += 1
    summary = dict(rule_version=RULE_VERSION, rdkit_version=rdBase.rdkitVersion,
                   total_rows=total, categorized_rows=categorized,
                   category_counts={label: counts[label] for label in CATEGORY_ORDER},
                   classification_status_counts=dict(statuses), overlap_counts=dict(overlaps),
                   rules=RULE_DESCRIPTIONS, role='Structure annotation only; no score or rank changes.')
    db.execute('INSERT INTO run_metadata VALUES (?,?)', ('chemical_families', json.dumps(summary)))
    return summary
