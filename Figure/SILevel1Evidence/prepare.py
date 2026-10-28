"""Prepare a complete, read-only Level 1 snapshot for both SI renderers."""
from bisect import bisect_right
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
MODULE = Path(__file__).resolve().parent
COMPONENTS = [
    ('P', 'Persistence_score', 'Persistence', 'hazard'),
    ('M', 'Mobility_score', 'Mobility', 'hazard'),
    ('B', 'Bioaccumulation_score', 'Bioaccumulation', 'hazard'),
    ('T', 'Toxicity_score', 'Toxicity', 'hazard'),
    ('FC', 'Exposure_food_contact_score', 'Food contact', 'exposure'),
    ('HB', 'Exposure_human_biomonitoring_score', 'Human biomonitoring', 'exposure'),
    ('Inv', 'Exposure_inventory_score', 'Inventory presence', 'exposure'),
    ('Prd', 'Exposure_production_score', 'Production / market', 'exposure'),
    ('Pat', 'Exposure_patent_score', 'Patents', 'exposure'),
    ('Lit', 'Exposure_literature_score', 'Literature', 'exposure'),
]
USES = {
    'Chemical intermediate or reagent': 'Intermediate / reagent',
    'Pesticide or biocide': 'Pesticide / biocide',
    'Contaminant or transformation product': 'Contaminant / transformation product',
    'Nutritional or cosmetic ingredient': 'Nutritional / cosmetic ingredient',
    'Heat transfer fluid or refrigerant': 'Heat-transfer fluid / refrigerant',
    'Polymerization or curing agent': 'Polymerization / curing agent',
    'Optical material or colorant': 'Optical material / colorant',
}
GIC = {
    'prohibited_or_phaseout': ('A', 'Prohibited / phase-out', '#54366E'),
    'restricted_or_authorisation_required': ('B', 'Restricted / authorisation', '#786086'),
    'candidate_or_high_concern': ('C', 'Candidate / high concern', '#A28EAE'),
    'monitoring_reporting_or_hazard_classification': ('D', 'Monitoring / reporting / hazard', '#CEC3D4'),
    'inventory_registration_or_use_only': ('E', 'Inventory / registration / use', '#EAE5ED'),
    'not_listed': ('N', 'No matched GIC listing', '#E3E6E9'),
    'auxiliary_identifier_only': ('I', 'Auxiliary identifier only', '#E3E6E9'),
    '': ('NA', 'Missing GIC annotation', '#E3E6E9'),
}
SCORE_FILL = {'0': '#FFFFFF', '0.25': '#EEF5F5', '0.5': '#DDEBEC', '1': '#A6C9CD', '2': '#326F78'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def number(value, field, missing=False):
    if value in ('', None) and missing:
        return None
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError(f'Invalid {field}: {value!r}') from error
    if not result.is_finite():
        raise ValueError(f'Nonfinite {field}')
    return int(result) if result == result.to_integral() else float(result)


def unique_by_key(rows, label):
    keys = [r.get('inchikey', '') for r in rows]
    if any(not k for k in keys) or len(keys) != len(set(keys)):
        raise ValueError(f'{label}: missing or duplicate InChIKey')
    return dict(zip(keys, rows))


def prepare_rows(records, annotations, config, policy):
    """No fixed population size, cohort size, category count or page count."""
    unique_by_key(records, 'Publication data')
    use_by_key = unique_by_key(annotations, 'Use annotations')
    if config.get('rounding') != 'half_up_after_domain_sum':
        raise ValueError('Unsupported source rounding rule; review the new scoring policy')
    cuts = policy['cutpoints']
    if len(cuts) != 3 or cuts != sorted(set(cuts)):
        raise ValueError('Expected three increasing domain-label cutpoints')
    if any(config['thresholds'][d] != cuts for d in ['hazard', 'exposure']):
        raise ValueError('Source thresholds differ from the selected five-level policy')
    matrix = policy['level_matrix_L_M_H_vH']
    if len(matrix) != 4 or any(len(r) != 4 for r in matrix):
        raise ValueError('Expected a 4 by 4 level matrix')
    components = [dict(abbreviation=a, field=f, name=n, domain=d,
                       weight=number(config[f'{d}_weights'][f], f'weight {f}')) for a,f,n,d in COMPONENTS]
    if any(c['weight'] < 0 for c in components):
        raise ValueError('Negative component weight')
    numeric = ['Hazard_score','Exposure_score','Priority_score','Priority_rank',
               'Hazard_score_raw','Exposure_score_raw'] + [c['field'] for c in components]
    selected, levels, issues = [], Counter(), []
    for original in records:
        row = dict(original)
        for field in numeric:
            row[field] = number(row.get(field), field, missing=field=='Priority_rank' or (field.endswith('_score') and field not in ['Hazard_score','Exposure_score','Priority_score']))
        h,e = row['Hazard_score'],row['Exposure_score']
        if any(not isinstance(v,int) or v < 0 for v in [h,e]):
            raise ValueError('Expected nonnegative integer domain scores')
        if any(Decimal(str(row[f'{domain}_score_raw'])).quantize(Decimal(1),rounding=ROUND_HALF_UP) != row[f'{domain}_score'] for domain in ['Hazard','Exposure']):
            raise ValueError('Source rounded scores disagree with original raw totals')
        if row['Priority_score'] != h+e:
            raise ValueError('Source priority score disagrees with H + E')
        label_indices = [bisect_right(cuts,h),bisect_right(cuts,e)]
        level = matrix[label_indices[0]][label_indices[1]]
        levels[level] += 1
        if level != 1:
            continue
        for component in components:
            value = row[component['field']]
            maximum = 1 if component['abbreviation'] in ['FC','HB'] else 2
            if value is not None and (str(value) not in SCORE_FILL or value > maximum):
                raise ValueError(f'Unsupported component score: {component["field"]}={value}')
        # Independent reconciliation only: exported totals/ranks remain source values.
        for domain in ['hazard','exposure']:
            total = sum(Decimal(str(row[c['field']] or 0))*Decimal(str(c['weight'])) for c in components if c['domain']==domain)
            if total != Decimal(str(row[f'{domain.title()}_score_raw'])):
                raise ValueError(f'Raw {domain} score does not match source component weights')
        if not isinstance(row['Priority_rank'],int) or row['Priority_rank'] < 1:
            raise ValueError('Invalid source competition rank')
        annotation = use_by_key.get(row['inchikey'], {})
        use = annotation.get('primary_use','').strip()
        changed_identity = [field for field in ['Name','CAS'] if annotation.get(field) and annotation[field] != row.get(field)]
        if changed_identity:
            issues.append({'inchikey':row['inchikey'],'issue':'Identity label changed: '+', '.join(changed_identity)})
        status = 'Pending classification' if not use else ('Identity labels need review' if changed_identity else 'User-supplied annotation')
        if not use:
            issues.append({'inchikey':row['inchikey'],'issue':'No primary-use annotation'})
        regulatory = row.get('GIC_regulatory_status','')
        if regulatory not in GIC:
            raise ValueError('Unmapped GIC category: '+regulatory)
        code,full_name,colour = GIC[regulatory]
        row.update(primary_use=use or 'Unclassified / pending review',
                   primary_use_display=USES.get(use,use) if use else 'Unclassified / pending review',
                   detailed_uses=annotation.get('detailed_uses',''),
                   annotation_id=annotation.get('record_id',''),
                   annotation_status=status,
                   annotation_source=annotation.get('source',annotation.get('citation','')),
                   annotation_review_status=annotation.get('review_status','Not independently verified'),
                   Source_priority_level=number(original['Priority_level'],'source level'),
                   Figure_priority_level=level,
                   Figure_hazard_label=['L','M','H','vH'][label_indices[0]],
                   Figure_exposure_label=['L','M','H','vH'][label_indices[1]],
                   Regulatory_code=code,Regulatory_name=full_name,Regulatory_colour=colour,
                   missing_components=', '.join(c['abbreviation'] for c in components if row[c['field']] is None))
        selected.append(row)
    selected.sort(key=lambda r:(-r['Priority_score'],r['inchikey']))
    for i,row in enumerate(selected,1):
        row['Display_order']=i
        row['Display_ID']=f'{i:03d}'
    selected_keys={r['inchikey'] for r in selected}
    changes={'unclassified':[r['inchikey'] for r in selected if r['annotation_status']=='Pending classification'],
             'annotation_keys_outside_cohort':sorted(set(use_by_key)-selected_keys), 'issues':issues}
    return selected,components,dict(sorted(levels.items())),changes


def make_payload(run_dir=None, annotations=None, policy_path=None):
    default=json.loads((MODULE/'source.json').read_text())
    run_dir=Path(run_dir).resolve() if run_dir else ROOT/default['run_dir']
    annotation=Path(annotations).resolve() if annotations else ROOT/default['annotations']
    policy_file=Path(policy_path).resolve() if policy_path else ROOT/default['policy']
    source=run_dir/'PlastPrior_results.csv'
    manifest_file=run_dir/'figure_data/_metadata/scenario_manifest.json'
    config_file=run_dir/'figure_data/_metadata/scoring_config.json'
    manifest=json.loads(manifest_file.read_text())
    config=json.loads(config_file.read_text())
    if sha(source) != manifest['csv_sha256'] or config != manifest['policy']:
        raise ValueError('CSV or scoring configuration does not match its run manifest')
    if run_dir == ROOT/default['run_dir'] and (sha(source)!=default['csv_sha256'] or manifest['run_id']!=default['run_id']):
        raise ValueError('Pinned default run changed')
    if annotations is None and sha(annotation)!=default['annotation_sha256']:
        raise ValueError('Pinned annotation file changed; use --annotations to select an explicit revised file')
    records=read_csv(source)
    if len(records)!=manifest['rows']:
        raise ValueError('Publication row count differs from run manifest')
    policy=json.loads(policy_file.read_text())
    rows,components,levels,changes=prepare_rows(records,read_csv(annotation),config,policy)
    if not rows:
        raise ValueError('No Level 1 compounds in this run; the existing review is preserved')
    sources={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in [source,manifest_file,config_file,annotation,policy_file]}
    return {'rows':rows,'components':components,'score_palette':SCORE_FILL,
            'regulatory_legend':[{'code':v[0],'label':v[1],'colour':v[2]} for v in GIC.values()],
            'metadata':{'run_id':manifest['run_id'],'cohort_size':len(rows),'population_size':len(records),
                        'policy_version':policy['version'],'level_counts':levels,'cutpoints':policy['cutpoints'],
                        'source_csv_sha256':sha(source),'annotation_sha256':sha(annotation),
                        'scoring_config':config,'sources':sources,
                        'annotation_status':'User-supplied primary and detailed uses; row-level citations were not supplied unless shown.',
                        'scope':'Five-level figure classification. Existing source scores, competition ranks and source priority levels are retained.'},
            'changes':changes}


def write_payload(payload, destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    (destination/'si_payload.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    with (destination/'compound_evidence.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(payload['rows'][0]));writer.writeheader();writer.writerows(payload['rows'])
    (destination/'annotation_changes.json').write_text(json.dumps(payload['changes'],ensure_ascii=False,indent=2)+'\n')
