"""Stage 6A: frozen exposure observations and eligibility, without scoring.

Canonical market records are historical derived inputs. This stage verifies
lineage and audits eligibility; it does not rerun their source transformations.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path, PurePosixPath
import platform
import shutil

import pandas as pd

from .inputs import _file_hash, resolve_data_root
from .evidence import _json, _read_csv
from .evidence_specialists import require_prediction_isolation
from .lrtp import _verify_outputs

DEFAULT_POLICY = Path(__file__).with_suffix('.json')
POLICY_HASH = _file_hash(DEFAULT_POLICY)
POLICY = json.loads(DEFAULT_POLICY.read_text(encoding='utf-8'))


def json_rows(path):
    with Path(path).open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def csv_rows(path, required=()):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not set(required) <= set(reader.fieldnames or []):
            raise ValueError(f'Missing input columns: {path.name}')
        for number, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'Malformed input row: {path.name}:{number}')
            yield number, row


def relative_file(root, relative):
    """Resolve portable manifest paths without allowing traversal or symlink escape."""
    ref = PurePosixPath(relative)
    if ref.is_absolute() or '..' in ref.parts or '\\' in relative or ':' in relative:
        raise ValueError('Invalid relative source path: ' + relative)
    result = root.joinpath(*ref.parts).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Source path escapes its input directory.')
    return result


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip().replace(',', ''))
    except InvalidOperation:
        return None
    return result if result.is_finite() and result >= 0 else None


def numeric_values(value):
    if isinstance(value, dict):
        return [n for v in value.values() for n in numeric_values(v)]
    if isinstance(value, list):
        return [n for v in value for n in numeric_values(v)]
    result = number(value)
    return [] if result is None else [result]


def market_eligibility(row, in_scope, registry):
    """Gate qualitative evidence independently of quantity availability."""
    common = []
    if not in_scope:
        common.append('outside_compound_universe')
    if row['identity_match_status'] not in POLICY['eligible_identity_statuses']:
        common.append('unaccepted_identity_mapping')
    if registry.get(row['source_id'], {}).get('selection_eligibility') != 'eligible_compound_numeric':
        common.append('source_not_eligible_for_compound_evidence')
    qualitative = list(common)
    if row['market_presence'] not in POLICY['presence_priority'] or POLICY['presence_priority'][row['market_presence']] == 0:
        qualitative.append('unknown_market_presence')
    quantitative = list(common)
    bounds = [number(row.get(k)) for k in ['quantity_lower_tonnes', 'quantity_upper_tonnes']]
    if not any(v is not None for v in bounds):
        quantitative.append('no_usable_numeric_quantity')
    if any(row.get(k, '').strip() and number(row[k]) is None for k in ['quantity_lower_tonnes', 'quantity_upper_tonnes']):
        quantitative.append('invalid_quantity_bound')
    if all(v is not None for v in bounds) and bounds[0] > bounds[1]:
        quantitative.append('inverted_quantity_bounds')
    if row.get('quantity_unit') not in POLICY['eligible_quantity_units']:
        quantitative.append('unsupported_quantity_unit')
    return {'qualitative_eligible': not qualitative, 'qualitative_exclusion_reasons': qualitative,
            'numeric_eligible': not quantitative, 'numeric_exclusion_reasons': quantitative}


def gic_tag_eligibility(resolution, listing, source_rows):
    tag = listing['list_tag']
    support = [sid for sid in resolution['matched_sids'] if tag in source_rows[sid]['local_list_tags']]
    reasons = []
    if resolution['match_method'] == 'chemical_name':
        reasons.append('name_only_association_requires_review')
    elif resolution['match_method'] not in {'cid_bridge', 'cas', 'inchikey'}:
        reasons.append('unaccepted_gic_match_method')
    if not support:
        reasons.append('no_direct_local_tag_on_matched_sid')
    if listing.get('is_auxiliary') or listing.get('regulatory_action_class') != 'inventory_registration_or_use_only':
        reasons.append('not_industrial_inventory_evidence')
    return {'eligible': not reasons, 'exclusion_reasons': reasons, 'direct_support_sids': support}


def external_eligibility(kind, row, in_scope, curated_positive=False, lite_positive=False):
    reasons = []
    if not in_scope:
        reasons.append('outside_compound_universe')
    count_field = 'pubchem_patent_count' if kind == 'patent' else 'pubmed_title_abstract_count'
    status_field = 'check_status' if kind == 'patent' else 'status'
    accepted = {'pubchem_patent_ids_found', 'pubchem_no_patent_ids'} if kind == 'patent' else {'ok'}
    if row[status_field] not in accepted:
        reasons.append('query_not_successfully_completed')
    count = number(row[count_field])
    if count is None or count != count.to_integral_value():
        reasons.append('invalid_or_missing_count')
    if row.get('error_message', '').strip():
        reasons.append('query_error')
    if kind == 'patent':
        existing = row.get('existing_patent_count', '').strip()
        if curated_positive or lite_positive:
            reasons.append('existing_nonzero_patent_evidence')
        if existing and number(existing) != 0:
            reasons.append('external_audit_not_for_zero_baseline')
        if row[status_field] == 'pubchem_no_patent_ids' and count != 0:
            reasons.append('status_count_conflict')
        if row[status_field] == 'pubchem_patent_ids_found' and (count is None or count <= 0):
            reasons.append('status_count_conflict')
    return {'eligible': not reasons, 'exclusion_reasons': reasons}


def verify_inputs(data_root):
    paths = {r['id']: data_root.joinpath(*r['parts']) for r in POLICY['inputs']}
    for entry in POLICY['inputs']:
        if _file_hash(paths[entry['id']]) != entry['sha256']:
            raise ValueError('Frozen exposure input changed: ' + entry['id'])
    read = lambda name: json.loads(paths[name].read_text(encoding='utf-8'))
    run, checkpoint, inputs = read('run_manifest'), read('stage6_checkpoint'), read('input_manifest')
    hashes = {r['id']: r['sha256'] for r in POLICY['inputs']}
    if run['stages']['6']['checkpoint_sha256'] != hashes['stage6_checkpoint'] or run['input_manifest_sha256'] != hashes['input_manifest']:
        raise ValueError('Broken frozen exposure manifest chain.')
    artifacts = {r['artifact_id']: r for r in checkpoint['artifacts']}
    for entry in POLICY['inputs']:
        if 'artifact_id' in entry:
            artifact = artifacts[entry['artifact_id']]
            if artifact['sha256'] != entry['sha256'] or artifact['path'] != entry['historical_path']:
                raise ValueError('Canonical exposure input differs from the frozen checkpoint.')
        if entry['role'] == 'frozen_source_input' and not any(r['filename'] == paths[entry['id']].name and r['sha256'] == entry['sha256'] for r in inputs['records']):
            raise ValueError('Source input is not bound to the frozen input manifest.')
    return paths


@dataclass
class ExposureInputsResult:
    bt_directory: Path
    data_root: Path
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    manifest: dict = field(default_factory=dict)

    def write_reports(self, output_directory):
        """Stream complete observation ledgers and publish a manifest after validation."""
        out = Path(output_directory).resolve()
        root = self.bt_directory.parent.parent
        if (out == root or root.is_relative_to(out) or out.is_relative_to(self.data_root)
                or any(out.is_relative_to(root / stage) for stage in ['stage2', 'stage3', 'stage4', 'stage5'])):
            raise ValueError('Exposure reports must not overwrite inputs or upstream outputs.')
        out.mkdir(parents=True, exist_ok=True)
        manifest_path = out / 'exposure_manifest.json'
        # An incomplete run must never retain a success manifest from a previous run.
        manifest_path.unlink(missing_ok=True)
        manifests = {'bt': self.bt_directory / 'bt_manifest.json', 'pm': root / 'stage5' / 'hazard_manifest.json',
                     'basic': root / 'stage4' / 'evidence_manifest.json',
                     'specialists': root / 'stage4' / '4b' / 'specialist_manifest.json',
                     'annotations': root / 'stage4' / '4c' / 'annotation_manifest.json'}
        hashes = {k: _file_hash(p) for k, p in manifests.items()}
        upstream = {k: json.loads(p.read_text(encoding='utf-8')) for k, p in manifests.items()}
        for key, path in manifests.items():
            _verify_outputs(path.parent, upstream[key])
        if upstream['bt']['upstream_manifests_sha256']['pm'] != hashes['pm']:
            raise ValueError('Exposure inputs mix different upstream runs.')
        for key in ['basic', 'specialists', 'annotations']:
            if upstream['pm']['upstream_manifests_sha256'][key] != hashes[key]:
                raise ValueError('Exposure evidence differs from the Stage 5 lineage.')
        if upstream['annotations']['upstream_manifest_sha256'] != hashes['specialists'] or upstream['specialists']['upstream_manifest_sha256']['basic'] != hashes['basic']:
            raise ValueError('Broken exposure evidence lineage.')
        if _file_hash(DEFAULT_POLICY) != POLICY_HASH:
            raise ValueError('Exposure policy changed; restart the process.')
        paths = verify_inputs(self.data_root)
        input_hashes = {r['id']: r['sha256'] for r in POLICY['inputs']}
        compounds = _read_csv(self.bt_directory / 'compound_pbmt_hazard.csv')
        if not compounds['bt_result_role'].eq('analysis_after_identity_isolation').all():
            raise ValueError('Exposure intake requires isolated Stage 5B analysis inputs.')
        require_prediction_isolation(compounds)
        keys = set(compounds['inchikey'])
        if len(keys) != len(compounds) or '' in keys:
            raise ValueError('Invalid or duplicate compound keys.')
        rows = compounds.to_dict('records')
        payloads = {r['inchikey']: json.loads(r['db_extract_info']) for r in rows}
        registry = {r['source_id']: r for _, r in csv_rows(paths['registry'])}
        registry['plastchem'] = {'selection_eligibility': 'eligible_compound_numeric'}
        written = []
        def csv_write(name, records, columns=None):
            destination = out / (name + '.csv')
            iterator = iter(records)
            first = next(iterator, None)
            fields = columns or (list(first) if first is not None else [])
            with destination.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
                writer.writeheader()
                if first is not None:
                    writer.writerow(first)
                writer.writerows(iterator)
            written.append(destination)
        def json_write(name, records):
            destination = out / (name + '.jsonl')
            with destination.open('w', encoding='utf-8') as handle:
                for record in records:
                    handle.write(_json(record) + '\n')
            written.append(destination)
        production_root = self.data_root.joinpath(*POLICY['production_root_parts'])
        verified = {}
        def verify_raw(relative, expected):
            signature = (relative, expected)
            if signature not in verified:
                observed = _file_hash(relative_file(production_root, relative)) if relative else ''
                if expected and observed != expected:
                    raise ValueError('Production raw-file fingerprint mismatch: ' + relative)
                verified[signature] = {'relative_path': relative, 'expected_sha256': expected, 'observed_sha256': observed,
                                       'verification_status': 'verified' if expected and relative else 'historical_hash_not_recorded'}
            return verified[signature]['verification_status']
        for _, record in csv_rows(paths['production_inputs'], ['relative_path', 'sha256']):
            verify_raw(record['relative_path'], record['sha256'])
        states = {key: {'inchikey': key, 'historical_best_presence': 'unknown', 'eligible_best_presence': 'unknown',
                        'historical_evidence_count': 0, 'qualitative_eligible_count': 0, 'numeric_eligible_count': 0,
                        'identity_excluded_count': 0, 'excluded_positive_presence_count': 0} for key in sorted(keys)}
        source_counts = defaultdict(Counter)
        def accumulate(row, gate, historical=True):
            source_counts[row['source_id']]['records'] += 1
            for flag in ['qualitative_eligible', 'numeric_eligible']:
                source_counts[row['source_id']][flag] += int(gate[flag])
            key = row['inchikey'].strip().upper()
            if key not in states:
                source_counts[row['source_id']]['outside_compound_universe'] += 1
                return
            state = states[key]
            presence = row['market_presence']
            for field_name, accepted in [('historical_best_presence', historical), ('eligible_best_presence', gate['qualitative_eligible'])]:
                if accepted and POLICY['presence_priority'].get(presence, 0) > POLICY['presence_priority'][state[field_name]]:
                    state[field_name] = presence
            state['historical_evidence_count'] += int(historical)
            state['qualitative_eligible_count'] += int(gate['qualitative_eligible'])
            state['numeric_eligible_count'] += int(gate['numeric_eligible'])
            state['identity_excluded_count'] += int('unaccepted_identity_mapping' in gate['qualitative_exclusion_reasons'])
            state['excluded_positive_presence_count'] += int(not gate['qualitative_eligible'] and presence in POLICY['positive_presence'])
        def market_records():
            for kind in ['production', 'market']:
                for ordinal, record in csv_rows(paths[kind], POLICY['canonical_fields']):
                    raw_paths = record['raw_relative_path'].split(';')
                    raw_hashes = record['raw_sha256'].split(';')
                    if len(raw_paths) != len(raw_hashes):
                        raise ValueError('Raw source paths and hashes are not paired.')
                    statuses = [verify_raw(path, digest) for path, digest in zip(raw_paths, raw_hashes)]
                    raw_status = 'verified' if all(s == 'verified' for s in statuses) else 'historical_hash_not_recorded'
                    gate = market_eligibility(record, record['inchikey'].strip().upper() in keys, registry)
                    accumulate(record, gate)
                    yield {'audit_id': f'{kind}:{ordinal}', 'input_sha256': input_hashes[kind], 'source_table': kind,
                           'source_row_number': ordinal, 'raw_verification_status': raw_status, **record,
                           **{k: _json(v) if isinstance(v, list) else v for k, v in gate.items()}}
        csv_write('market_source_records', market_records())
        def legacy_records():
            for key in sorted(keys):
                for scope, sources in payloads[key].get('exposure', {}).get('production', {}).items():
                    for source, values in sources.items():
                        for index, raw in enumerate(values if isinstance(values, list) else [values]):
                            value = number(raw)
                            accepted = source == 'PlastChem' and value is not None
                            reason = '' if accepted else 'unsupported_production_source' if source != 'PlastChem' else 'invalid_quantity'
                            record = {'inchikey': key, 'source_id': 'plastchem' if source == 'PlastChem' else source,
                                      'market_presence': 'unknown' if value is None else 'confirmed_positive_quantity' if value > 0 else 'confirmed_zero_quantity'}
                            gate = {'qualitative_eligible': accepted, 'numeric_eligible': accepted,
                                    'qualitative_exclusion_reasons': [] if accepted else [reason]}
                            accumulate(record, gate, historical=accepted)
                            yield {**record, 'audit_id': f'legacy:{key}:{scope}:{source}:{index}',
                                   'record_id': f'plastchem:{key}:{scope}:{index}' if source == 'PlastChem' else '',
                                   'field_path': 'exposure.production.' + scope, 'source_db': source, 'value_index': index,
                                   'raw_value_json': _json(raw), 'eligible': accepted, 'exclusion_reason': reason,
                                   'identity_match_status': 'legacy_inchikey_compound_record',
                                   'lineage': 'exposure_source_links.jsonl; Stage 5B db_extract_info',
                                   'upstream_manifest_sha256': hashes['bt']}
        csv_write('legacy_production_records', legacy_records())
        for state in states.values():
            state['presence_changed_by_gate'] = state['historical_best_presence'] != state['eligible_best_presence']
        csv_write('market_gate_audit', states.values())
        csv_write('raw_file_verification', [verified[k] for k in sorted(verified)])
        csv_write('market_source_summary', [{'source_id': k, **{c: v[c] for c in ['records', 'qualitative_eligible', 'numeric_eligible', 'outside_compound_universe']}} for k, v in sorted(source_counts.items())])

        # Preserve every external query row, including failures and out-of-scope queries.
        lite_positive = set()
        lite_keys = Counter()
        def lite_records():
            for ordinal, record in csv_rows(paths['pubchemlite'], ['InChIKey', 'Patent_Count']):
                key = record['InChIKey'].strip().upper()
                count = number(record['Patent_Count'])
                eligible = key in keys and count is not None and count == count.to_integral_value()
                if eligible and count > 0:
                    lite_positive.add(key)
                if key in keys:
                    lite_keys[key] += 1
                yield {'audit_id': f'pubchemlite:{ordinal}', 'input_sha256': input_hashes['pubchemlite'],
                       'compound_key': key, 'raw_fields': record, 'eligible': eligible,
                       'exclusion_reasons': [] if eligible else ['outside_compound_universe' if key not in keys else 'invalid_or_missing_count']}
        json_write('pubchemlite_patent_records', lite_records())
        external_counts = {}
        external_status = defaultdict(dict)
        for kind in ['patent', 'pubmed']:
            seen, counts = set(), Counter()
            required = ['Inchikey_std', 'error_message'] + (['check_status', 'pubchem_patent_count', 'existing_patent_count'] if kind == 'patent' else ['status', 'pubmed_title_abstract_count'])
            def external_records():
                for ordinal, record in csv_rows(paths[kind], required):
                    key = record['Inchikey_std'].strip().upper()
                    if not key or key in seen:
                        raise ValueError('Duplicate or empty external evidence key: ' + kind)
                    seen.add(key)
                    curated = numeric_values(payloads.get(key, {}).get('exposure', {}).get('patent', {}))
                    gate = external_eligibility(kind, record, key in keys, any(n > 0 for n in curated), key in lite_positive)
                    counts['records'] += 1
                    counts['eligible'] += int(gate['eligible'])
                    counts['outside_compound_universe'] += int(key not in keys)
                    external_status[key][kind + '_eligible'] = gate['eligible']
                    external_status[key][kind + '_exclusion_reasons'] = _json(gate['exclusion_reasons'])
                    yield {'audit_id': f'{kind}:{ordinal}', 'input_sha256': input_hashes[kind],
                           'compound_key': key, 'raw_fields': record, **gate,
                           'curated_nonzero_patent_evidence': any(n > 0 for n in curated) if kind == 'patent' else None,
                           'pubchemlite_nonzero_patent_evidence': key in lite_positive if kind == 'patent' else None,
                           'interpretation': 'zero_baseline_correction_eligibility_only' if kind == 'patent' else 'unreviewed_title_abstract_query_hits'}
            json_write(kind + '_records', external_records())
            if kind == 'pubmed' and not keys <= seen:
                raise ValueError('Frozen PubMed query coverage is incomplete.')
            external_counts[kind] = dict(counts)

        # Direct tag support is evaluated across the union of matched SIDs.
        annotations = manifests['annotations'].parent
        gic_sources = {r['sid']: r for r in json_rows(annotations / 'gic_source_rows.jsonl')}
        gic_compounds = []
        def gic_records():
            for ordinal, resolution in enumerate(json_rows(annotations / 'gic_resolution_audit.jsonl'), 1):
                eligible_tags, excluded_tags = [], []
                for listing in resolution['listings']:
                    gate = gic_tag_eligibility(resolution, listing, gic_sources)
                    (eligible_tags if gate['eligible'] else excluded_tags).append(listing['list_tag'])
                    yield {'compound_key': resolution['compound_key'], 'list_tag': listing['list_tag'], **gate,
                           'matched_sids': resolution['matched_sids'], 'match_method': resolution['match_method'],
                           'metadata': listing, 'historical_metadata_hash_available': False,
                           'resolution_line_number': ordinal, 'annotation_manifest_sha256': hashes['annotations'],
                           'source_records': [{k: gic_sources[sid][k] for k in ['sid', 'source_filename', 'source_sha256', 'source_line_number', 'local_list_tags', 'shared_identifier_added_tags']} for sid in resolution['matched_sids']]}
                unresolved = resolution['match_method'] == 'chemical_name'
                unavailable = resolution['inventory_data_status'] != 'available'
                gic_compounds.append({'inchikey': resolution['compound_key'], 'match_method': resolution['match_method'],
                                      'historical_inventory_tags_json': _json(resolution['inventory_list_tags']),
                                      'historical_inventory_count': resolution['inventory_listing_count'],
                                      'eligible_inventory_tags_json': _json(sorted(set(eligible_tags))),
                                      'eligible_inventory_count': '' if unresolved or unavailable else len(set(eligible_tags)),
                                      'eligibility_status': 'name_association_review_required' if unresolved else 'lookup_unavailable' if unavailable else 'completed_lookup',
                                      'excluded_tags_json': _json(sorted(set(excluded_tags))),
                                      'lookup_attempts_json': _json(resolution['lookup_attempts']),
                                      'metadata_limit': 'frozen_classification_historical_acquisition_hash_unavailable'})
        json_write('gic_tag_eligibility', gic_records())
        if len(gic_compounds) != len(keys) or {r['inchikey'] for r in gic_compounds} != keys:
            raise ValueError('GIC eligibility audit has incomplete identities.')
        csv_write('gic_compound_audit', gic_compounds)
        gic_by_key = {r['inchikey']: r for r in gic_compounds}
        source_links = (r for r in json_rows(root / 'stage4' / 'basic_evidence_audit.jsonl') if r.get('field_path', '').startswith('exposure.'))
        json_write('exposure_source_links', source_links)
        # These existing specialist decisions retain the distinction between source membership and detection.
        def compound_records():
            for row in rows:
                key = row['inchikey']
                yield {'inchikey': key, 'representative_record_id': row['representative_record_id'],
                       **{k: row[k] for k in ['qsar_identity_status', 'qsar_identity_reason', 'qsar_evidence_available', 'lrtp_available', 'gic_name_review_required', 'gic_shared_identifier_tag_expansion', 'source_tables_json', 'litchemplast_evidence_available', 'fcchumon_evidence_available', 'fcchumon_evidence_status', 'fcchumon_detected']},
                       'specialist_resolution_json': _json({k: payloads[key].get(k) for k in ['litchemplast_resolution', 'fcchumon_resolution']}),
                       **{k: v for k, v in states[key].items() if k != 'inchikey'},
                       'gic_eligibility_status': gic_by_key[key]['eligibility_status'],
                       'eligible_inventory_count': gic_by_key[key]['eligible_inventory_count'],
                       'pubchemlite_record_count': lite_keys[key],
                       **{f'{kind}_{suffix}': external_status[key].get(f'{kind}_{suffix}', False if suffix == 'eligible' else '["no_frozen_query_record"]') for kind in ['patent', 'pubmed'] for suffix in ['eligible', 'exclusion_reasons']},
                       'result_role': 'exposure_evidence_eligibility_only'}
        csv_write('compound_exposure_evidence', compound_records())
        for name in ['identity_review_source_links.jsonl']:
            shutil.copyfile(self.bt_directory / name, out / name)
            written.append(out / name)
        mappings = [{'source': 'canonical_production_and_market', 'source_field': c, 'target': 'market_source_records.' + c,
                     'transformation': 'verbatim; row multiplicity retained'} for c in POLICY['canonical_fields']]
        mappings += [
            {'source': 'Stage 5B', 'source_field': 'db_extract_info.exposure.production', 'target': 'legacy_production_records', 'transformation': 'retain all observations; only finite nonnegative PlastChem values eligible'},
            {'source': 'Stage 4A', 'source_field': 'basic_evidence_audit.field_path=exposure.*', 'target': 'exposure_source_links', 'transformation': 'verbatim selected and excluded source observations'},
            {'source': 'Stage 4B', 'source_field': 'litchemplast_resolution;fcchumon_resolution;source_tables_json', 'target': 'compound_exposure_evidence', 'transformation': 'preserve associations, detection status and membership separately'},
            {'source': 'GIC', 'source_field': 'listings;match_method;matched_sids;local_list_tags', 'target': 'gic_tag_eligibility', 'transformation': 'name gate; matched-SID direct local support; industrial inventory classification'},
            {'source': 'PubChemLite', 'source_field': 'InChIKey;Patent_Count', 'target': 'pubchemlite_patent_records', 'transformation': 'full key strip/upper; nonnegative integer eligibility; all rows retained'},
            {'source': 'patent', 'source_field': 'Inchikey_std;check_status;pubchem_patent_count;existing_patent_count;error_message', 'target': 'patent_records', 'transformation': 'full key strip/upper; completed query and zero-baseline eligibility; no count selected'},
            {'source': 'PubMed', 'source_field': 'Inchikey_std;status;pubmed_title_abstract_count;error_message', 'target': 'pubmed_records', 'transformation': 'full key strip/upper; completed query; retain terms, query, URL and date; no identity confirmation'}]
        for kind in ['patent', 'pubmed', 'pubchemlite']:
            with paths[kind].open(encoding='utf-8-sig', newline='') as handle:
                columns = next(csv.reader(handle))
            mappings.extend({'source': kind, 'source_field': column,
                             'target': ('pubchemlite_patent' if kind == 'pubchemlite' else kind) + '_records.raw_fields.' + column,
                             'transformation': 'verbatim; normalized keys and eligibility are separate audit fields'}
                            for column in columns)
        csv_write('exposure_field_mapping', mappings)
        counts = {'compounds': len(keys), 'canonical_records': sum(v['records'] for k, v in source_counts.items() if k in registry and k != 'plastchem'),
                  'legacy_plastchem_records': source_counts['plastchem']['numeric_eligible'],
                  'identity_review_compounds': int(compounds['qsar_identity_status'].eq('review_required').sum()),
                  'identity_review_source_links': sum(1 for _ in json_rows(out / 'identity_review_source_links.jsonl')),
                  'identity_excluded_market_records': sum(s['identity_excluded_count'] for s in states.values()),
                  'compounds_with_market_presence_change': sum(s['presence_changed_by_gate'] for s in states.values()),
                  'gic_name_review_compounds': sum(r['match_method'] == 'chemical_name' for r in gic_compounds),
                  'gic_shared_identifier_review_compounds': int(compounds['gic_shared_identifier_tag_expansion'].eq('True').sum()),
                  'raw_file_verification_records': len(verified), 'raw_hash_gaps': sum(r['verification_status'] != 'verified' for r in verified.values())}
        for kind, values in external_counts.items():
            counts.update({kind + '_' + k: v for k, v in values.items()})
        self.summary = pd.DataFrame([{'measure': k, 'count': v} for k, v in counts.items()])
        csv_write('exposure_summary', self.summary.to_dict('records'))
        for key, path in manifests.items():
            if _file_hash(path) != hashes[key]:
                raise ValueError('Upstream manifest changed during exposure intake.')
            _verify_outputs(path.parent, upstream[key])
        verify_inputs(self.data_root)
        for (relative, _), record in verified.items():
            if relative and _file_hash(relative_file(production_root, relative)) != record['observed_sha256']:
                raise ValueError('Raw input changed during exposure intake: ' + relative)
        require_prediction_isolation(compounds)
        if _file_hash(DEFAULT_POLICY) != POLICY_HASH:
            raise ValueError('Exposure policy changed during intake.')
        self.manifest = {'schema_version': 1, 'stage': '6A', 'scope': POLICY['scope'], 'policy_sha256': POLICY_HASH,
                         'implementation_sha256': _file_hash(Path(__file__)), 'upstream_manifests_sha256': hashes,
                         'input_sha256': input_hashes, 'counts': counts, 'external_counts': external_counts,
                         'rules': POLICY['rules'], 'new_scores_computed': False, 'numeric_maxima_selected': False,
                         'runtime': {'python': platform.python_version(), 'pandas': pd.__version__},
                         'output_sha256': {p.name: _file_hash(p) for p in written}}
        manifest_path.write_text(json.dumps(self.manifest, indent=2) + '\n', encoding='utf-8')


def integrate_exposure_evidence(bt_results, data_root=None):
    """Prepare Stage 6A; write_reports streams and validates the large ledgers."""
    return ExposureInputsResult(Path(bt_results).resolve(), resolve_data_root("data" if data_root is None else data_root).resolve())
