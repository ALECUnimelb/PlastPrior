"""Read-only structural annotation for the complete five-level Level 1 cohort.

RDKit is used only for molecular data verification and classification. All
visuals are produced by build.R. These mutually exclusive display groups are
not an ontology, an inferred plastic function, or a new prioritisation policy.
"""
import csv
import hashlib
import json
from pathlib import Path
from rdkit import Chem, rdBase
from rdkit.Chem import inchi

ROOT = Path('/Users/ruiwang/Projects/APPs/PlastPrior')
MODULE = ROOT / 'Figure/Level1Identity'
DATA = ROOT / 'output/figure_data/Level1Identity/review'
INPUT = ROOT / 'Figure/Level1Evidence/inputs/Level1_101_aligned_uses_en.csv'
RESULT = ROOT / 'output/2026-10-27/PlastPrior_results.csv'
POLICY = ROOT / 'Figure/_shared/five_level_policy.json'
GROUPS = {
 'hal_non_aromatic': 'Halogenated non-aromatics',
 'hal_aromatic_chx': 'Halogenated aromatics: C/H/X',
 'hal_aromatic_o': 'Halogenated aromatics: oxygen',
 'hal_aromatic_ns': 'Halogenated aromatics: nitrogen / sulfur',
 'hal_heterocycle': 'Halogenated heteroaromatics',
 'nonhal_heterocycle': 'Non-halogenated heteroaromatics',
 'nonhal_aromatic_ch': 'Aromatic hydrocarbons',
 'nonhal_o': 'Non-halogenated oxygen compounds',
 'nonhal_other': 'Other non-halogenated compounds',
}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def classify(mol):
    elements = {a.GetAtomicNum() for a in mol.GetAtoms()}
    aromatic = any(a.GetIsAromatic() for a in mol.GetAtoms())
    heteroaromatic = any(a.GetIsAromatic() and a.GetAtomicNum() != 6 for a in mol.GetAtoms())
    halogen = bool(elements & {9, 17, 35, 53})
    if halogen:
        if not aromatic:
            group = 'hal_non_aromatic'
        elif heteroaromatic:
            group = 'hal_heterocycle'
        elif elements & {7, 16}:
            group = 'hal_aromatic_ns'
        elif 8 in elements:
            group = 'hal_aromatic_o'
        else:
            assert elements <= {1, 6, 9, 17, 35, 53}
            group = 'hal_aromatic_chx'
    elif heteroaromatic:
        group = 'nonhal_heterocycle'
    elif 8 in elements:
        group = 'nonhal_o'
    elif aromatic and elements <= {1, 6}:
        group = 'nonhal_aromatic_ch'
    else:
        group = 'nonhal_other'
    return group, halogen, aromatic, heteroaromatic, elements

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in (INPUT, RESULT, POLICY)}
    lock = json.loads((ROOT / 'Figure/managed_sources.json').read_text())
    assert sha(RESULT) == lock['files']['publication']['sha256']
    inputs, full = read(INPUT), read(RESULT)
    lookup = {r['inchikey']: r for r in full}
    assert len(lookup) == len(full) == 15125
    policy = json.loads(POLICY.read_text())
    def level(r):
        hi = sum(float(r['Hazard_score']) >= v for v in policy['cutpoints'])
        ei = sum(float(r['Exposure_score']) >= v for v in policy['cutpoints'])
        return policy['level_matrix_L_M_H_vH'][hi][ei]
    expected = {r['inchikey'] for r in full if level(r) == 1}
    assert len(inputs) == len(expected) == 101
    assert {r['inchikey'] for r in inputs} == expected
    annotated = []
    for inp in inputs:
        r = lookup[inp['inchikey']]
        assert r['Name'] == inp['Name'] and r['CAS'] == inp['CAS']
        mol = Chem.MolFromSmiles(r['SMILES'])
        assert mol is not None, inp['record_id']
        regenerated_key = inchi.MolToInchiKey(mol)
        assert regenerated_key == r['inchikey'], inp['record_id']
        group, halogen, aromatic, heteroaromatic, elements = classify(mol)
        annotated.append({
            **inp, 'SMILES': r['SMILES'], 'structure_group': group,
            'group_label': GROUPS[group], 'contains_halogen': halogen,
            'contains_aromatic_atom': aromatic, 'contains_heteroaromatic_atom': heteroaromatic,
            'atomic_numbers': ';'.join(map(str, sorted(elements))),
            'regenerated_inchikey': regenerated_key, 'Figure_priority_level': 1,
            **{k: r[k] for k in ('Hazard_score', 'Exposure_score', 'Priority_score', 'Priority_rank', 'Top_n_selected')},
        })
    with (DATA / 'compound_identity.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(annotated[0]))
        writer.writeheader(); writer.writerows(annotated)
    counts = {g: sum(r['structure_group'] == g for r in annotated) for g in GROUPS}
    assert sum(counts.values()) == 101 and all(counts.values())
    assert all(sha(ROOT / p) == h for p, h in hashes.items())
    report = {
        'cohort_count': 101, 'unique_inchikeys': 101, 'smiles_parsed': 101,
        'exact_regenerated_inchikey_matches': 101, 'excluded_rows': 0,
        'rdkit_version': rdBase.rdkitVersion, 'source_hashes': hashes,
        'group_counts': counts, 'group_labels': GROUPS,
        'classification_scope': 'Mutually exclusive structure-based display groups for this cohort only',
        'ordered_rules': [
            'Halogen means an F, Cl, Br or I atom anywhere in the complete structure.',
            'Among halogen-containing compounds: no aromatic atom -> non-aromatics.',
            'Otherwise an aromatic non-carbon atom -> heteroaromatics.',
            'Otherwise N or S anywhere -> nitrogen/sulfur aromatics (may also contain O).',
            'Otherwise O anywhere -> oxygen aromatics (including phenolate salt).',
            'Otherwise C/H/halogen-only aromatic structure -> C/H/X aromatics.',
            'Among non-halogenated compounds: heteroaromatic atoms take precedence, then O, then C/H-only aromatics, then other.',
        ],
        'source_scores_ranks_preserved': True,
        'display_order': 'Alphabetical names within structural groups; grouping order is for layout, not rank',
    }
    (DATA / 'classification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'cohort': 101, 'exact_identity_matches': 101, 'groups': counts}))

if __name__ == '__main__':
    main()
