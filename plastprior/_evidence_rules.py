"""Frozen source-field rules for Stage 4A, separated from file I/O and provenance.

Source-native hazard scores are retained as observations, never recalculated.
Database-derived identity fields describe historical evidence selection and must
not overwrite the canonical chemical identities established in Stage 2.
"""
from __future__ import annotations
import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

FIELD_RULES = json.loads(Path(__file__).with_name("evidence_fields.json").read_text(encoding="utf-8"))["field_rules"]

def unify_compound_record(json_input: dict) -> dict:
    """Apply the frozen field-selection rules without changing canonical Stage 2 identities."""

    def _is_nullish(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str) and v.strip() == '':
            return True
        if isinstance(v, float) and math.isnan(v):
            return True
        return False

    def _norm_str(v: Any) -> Optional[str]:
        if _is_nullish(v):
            return None
        return str(v).strip()

    def _norm_inchikey(v: Any) -> Optional[str]:
        s = _norm_str(v)
        return s.upper() if s else None

    def _norm_cas(v: Any) -> Optional[str]:
        s = _norm_str(v)
        return s if s else None

    def _truthy(v: Any) -> bool:
        if _is_nullish(v):
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v != 0
        if isinstance(v, str):
            s = v.strip().lower()
            return s in {'1', 'true', 't', 'yes', 'y', 'present', 'listed', 'positive'}
        return bool(v)

    def _as_float(v: Any) -> Optional[float]:
        if _is_nullish(v):
            return None
        try:
            return float(v)
        except Exception:
            return None

    def _mk_audit_entry(*, db: str, row_index: Any, match_type: Any, match_col: Any, match_value: Any, source_col: str, raw_value: Any, selected: Optional[bool]=None) -> dict:
        entry = {'db': db, 'row_index': row_index, 'match_type': match_type, 'match_col': match_col, 'match_value': match_value, 'source_col': source_col, 'raw_value': raw_value}
        if selected is not None:
            entry['selected'] = selected
        return entry

    def _add_mismatch(*, field_path: str, db: str, row_index: Any, match_type: Any, match_value: Any, source_col: Any, raw_value: Any, reason: str) -> None:
        unified['mismatch_report'].append({'field_path': field_path, 'db': db, 'row_index': row_index, 'match_type': match_type, 'match_value': match_value, 'source_col': source_col, 'raw_value': raw_value, 'reason': reason})

    def _iter_db_matches(per_db_obj: dict) -> List[Tuple[str, dict]]:
        """
        Yields (db_name, match_obj) where match_obj contains:
          - match_type, match_col, match_value, row_index, data
        """
        out: List[Tuple[str, dict]] = []
        if not isinstance(per_db_obj, dict):
            return out
        for db, payload in per_db_obj.items():
            if not isinstance(payload, dict):
                continue
            matches = payload.get('matches')
            if isinstance(matches, list):
                for m in matches:
                    if isinstance(m, dict):
                        out.append((db, m))
        return out

    def _get_identity_seed(inp: dict) -> dict:
        """
        Prefer json_input['identity'] if present, otherwise infer from best-quality DB match rows.
        """
        if isinstance(inp.get('identity'), dict):
            ident = inp['identity'].copy()
            return {'inchikey': _norm_inchikey(ident.get('inchikey') or ident.get('InChIKey') or ident.get('Inchikey')), 'cas': _norm_cas(ident.get('cas') or ident.get('CAS') or ident.get('casrn') or ident.get('CASRN')), 'smiles': _norm_str(ident.get('smiles') or ident.get('SMILES') or ident.get('Smile') or ident.get('Smile_std')), 'name': _norm_str(ident.get('name') or ident.get('Name')), 'formula': _norm_str(ident.get('formula') or ident.get('Formula') or ident.get('molecular_formula')), 'monoisotopic_mass': ident.get('monoisotopic_mass')}
        db_priority = FIELD_RULES['db_priority']
        per_db = inp.get('per_db', {}) if isinstance(inp.get('per_db'), dict) else {}
        all_matches = _iter_db_matches(per_db)

        def _db_rank(db: str) -> int:
            try:
                return db_priority.index(db)
            except ValueError:
                return len(db_priority) + 999
        all_matches.sort(key=lambda x: (_db_rank(x[0]), x[1].get('row_index', 10 ** 9)))

        def _colpick(d: dict, keys: List[str]) -> Any:
            for k in keys:
                if k in d and (not _is_nullish(d.get(k))):
                    return d.get(k)
            return None
        inferred = {'inchikey': None, 'cas': None, 'smiles': None, 'name': None, 'formula': None, 'monoisotopic_mass': None}
        for db, m in all_matches:
            row = m.get('data') or {}
            if not isinstance(row, dict):
                continue
            inferred['inchikey'] = inferred['inchikey'] or _norm_inchikey(_colpick(row, ['InChIKey', 'InChI_key', 'Inchikey', 'InChI_Key', 'inchikey']))
            inferred['cas'] = inferred['cas'] or _norm_cas(_colpick(row, ['CAS', 'CASRN', 'CASRN ', 'Cas', 'cas']))
            inferred['smiles'] = inferred['smiles'] or _norm_str(_colpick(row, ['SMILES', 'Smile', 'Smile_std', 'smiles']))
            inferred['name'] = inferred['name'] or _norm_str(_colpick(row, ['Name', 'name', 'PreferredName']))
            inferred['formula'] = inferred['formula'] or _norm_str(_colpick(row, ['Formula', 'Molecular_formula', 'molecular_formula']))
            mm = _colpick(row, ['MonoisotopicMass', 'monoisotopic_mass', 'Molecular_Mass_Isotope'])
            inferred['monoisotopic_mass'] = inferred['monoisotopic_mass'] or (_as_float(mm) if mm is not None else None)
            if inferred['inchikey'] or inferred['cas']:
                break
        return inferred

    def _validate_strict_identity(db: str, m: dict, identity: dict) -> bool:
        mt = _norm_str(m.get('match_type')) or ''
        mv = m.get('match_value')
        row = m.get('data') or {}
        row_index = m.get('row_index')
        if mt == 'cas':
            ident_cas = _norm_cas(identity.get('cas'))
            mv_cas = _norm_cas(mv)
            if not ident_cas:
                _add_mismatch(field_path='identity.cas', db=db, row_index=row_index, match_type=mt, match_value=mv, source_col=m.get('match_col'), raw_value=mv, reason='Strict CAS validation failed: identity.cas is missing')
                return False
            if mv_cas != ident_cas:
                _add_mismatch(field_path='identity.cas', db=db, row_index=row_index, match_type=mt, match_value=mv, source_col=m.get('match_col'), raw_value=mv, reason=f'Strict CAS validation failed: match_value ({mv_cas}) != identity.cas ({ident_cas})')
                return False
            return True
        if mt == 'inchikey':
            ident_ik = _norm_inchikey(identity.get('inchikey'))
            mv_ik = _norm_inchikey(mv)
            if not ident_ik:
                _add_mismatch(field_path='identity.inchikey', db=db, row_index=row_index, match_type=mt, match_value=mv, source_col=m.get('match_col'), raw_value=mv, reason='Strict InChIKey validation failed: identity.inchikey is missing')
                return False
            if mv_ik != ident_ik:
                _add_mismatch(field_path='identity.inchikey', db=db, row_index=row_index, match_type=mt, match_value=mv, source_col=m.get('match_col'), raw_value=mv, reason=f'Strict InChIKey validation failed: match_value ({mv_ik}) != identity.inchikey ({ident_ik})')
                return False
            return True
        if mt == 'smiles':
            return True
        _add_mismatch(field_path='audit_trail.match_type', db=db, row_index=row_index, match_type=mt, match_value=mv, source_col=m.get('match_col'), raw_value=mv, reason='Unknown match_type; excluded to prevent cross-substance contamination')
        return False

    def _extract_first_identity_field(field_key: str, field_path: str, candidates_by_db: Dict[str, List[str]], valid_rows: List[Tuple[str, dict]], normalizer) -> Optional[Any]:
        """
        Identity fields are selected from highest-quality DB available (db_priority order).
        Still records ALL candidate observations in audit_trail[field_path].
        """
        selected_value = None
        selected_from = None
        for db, m in valid_rows:
            row = m.get('data') or {}
            if not isinstance(row, dict):
                continue
            cols = candidates_by_db.get(db, []) + candidates_by_db.get('*', [])
            for col in cols:
                if col in row and (not _is_nullish(row.get(col))):
                    raw = row.get(col)
                    val = normalizer(raw)
                    if _is_nullish(val):
                        continue
                    unified['audit_trail'].setdefault(field_path, []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=col, raw_value=raw, selected=False))
                    if selected_value is None:
                        selected_value = val
                        selected_from = (db, m.get('row_index'), col, raw)
        if selected_from is not None:
            db_sel, row_idx_sel, col_sel, raw_sel = selected_from
            entries = unified['audit_trail'].get(field_path, [])
            for e in entries:
                if e.get('db') == db_sel and e.get('row_index') == row_idx_sel and (e.get('source_col') == col_sel) and (e.get('raw_value') == raw_sel):
                    e['selected'] = True
                    break
        return selected_value

    def _add_multi_observations(*, out_container: dict, out_key: str, field_path: str, candidates_by_db: Dict[str, List[str]], valid_rows: List[Tuple[str, dict]], normalizer=lambda x: x, keep_per_db: bool=True) -> None:
        """
        Adds observations as a list (or per-db dict of lists) and writes audit trail entries.
        """
        if keep_per_db:
            out_container.setdefault(out_key, {})
        else:
            out_container.setdefault(out_key, [])
        for db, m in valid_rows:
            row = m.get('data') or {}
            if not isinstance(row, dict):
                continue
            cols = candidates_by_db.get(db, []) + candidates_by_db.get('*', [])
            for col in cols:
                if col not in row:
                    continue
                raw = row.get(col)
                if _is_nullish(raw):
                    continue
                val = normalizer(raw)
                if _is_nullish(val):
                    continue
                if keep_per_db:
                    out_container[out_key].setdefault(db, [])
                    if val not in out_container[out_key][db]:
                        out_container[out_key][db].append(val)
                elif val not in out_container[out_key]:
                    out_container[out_key].append(val)
                unified['audit_trail'].setdefault(field_path, []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=col, raw_value=raw))
    unified: dict = {'identity': {}, 'hazard': {}, 'exposure': {'human': {}, 'migration': {}, 'production': {}, 'environment': {}, 'patent': {}, 'literature': {}}, 'regulatory_listings': {}, 'classification': {}, 'audit_trail': {}, 'mismatch_report': []}
    identity_seed = _get_identity_seed(json_input)
    per_db = json_input.get('per_db', {}) if isinstance(json_input.get('per_db'), dict) else {}
    all_matches = _iter_db_matches(per_db)
    db_priority = FIELD_RULES['db_priority']

    def _db_rank(db: str) -> int:
        try:
            return db_priority.index(db)
        except ValueError:
            return len(db_priority) + 999
    valid_rows: List[Tuple[str, dict]] = []
    for db, m in all_matches:
        if _validate_strict_identity(db, m, identity_seed):
            valid_rows.append((db, m))
    valid_rows.sort(key=lambda x: (_db_rank(x[0]), x[1].get('row_index', 10 ** 9)))
    identity_cols = FIELD_RULES['identity_cols']
    unified['identity']['inchikey'] = _extract_first_identity_field('inchikey', 'identity.inchikey', identity_cols['inchikey'], valid_rows, _norm_inchikey) or identity_seed.get('inchikey')
    unified['identity']['cas'] = _extract_first_identity_field('cas', 'identity.cas', identity_cols['cas'], valid_rows, _norm_cas) or identity_seed.get('cas')
    unified['identity']['smiles'] = _extract_first_identity_field('smiles', 'identity.smiles', identity_cols['smiles'], valid_rows, _norm_str) or identity_seed.get('smiles')
    unified['identity']['name'] = _extract_first_identity_field('name', 'identity.name', identity_cols['name'], valid_rows, _norm_str) or identity_seed.get('name')
    unified['identity']['formula'] = _extract_first_identity_field('formula', 'identity.formula', identity_cols['formula'], valid_rows, _norm_str) or identity_seed.get('formula')
    mm_val = _extract_first_identity_field('monoisotopic_mass', 'identity.monoisotopic_mass', identity_cols['monoisotopic_mass'], valid_rows, _as_float)
    unified['identity']['monoisotopic_mass'] = mm_val if mm_val is not None else identity_seed.get('monoisotopic_mass')
    hazard_cols = FIELD_RULES['hazard_cols']
    for k, cmap in hazard_cols.items():
        _add_multi_observations(out_container=unified['hazard'], out_key=k, field_path=f'hazard.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    tox_label_cols = FIELD_RULES['tox_label_cols']
    _add_multi_observations(out_container=unified['hazard'], out_key='toxicological_labels', field_path='hazard.toxicological_labels', candidates_by_db=tox_label_cols, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    human_cols = FIELD_RULES['human_cols']
    for k, cmap in human_cols.items():
        _add_multi_observations(out_container=unified['exposure']['human'], out_key=k, field_path=f'exposure.human.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    migration_cols = FIELD_RULES['migration_cols']
    for k, cmap in migration_cols.items():
        _add_multi_observations(out_container=unified['exposure']['migration'], out_key=k, field_path=f'exposure.migration.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    production_cols = FIELD_RULES['production_cols']
    for k, cmap in production_cols.items():
        _add_multi_observations(out_container=unified['exposure']['production'], out_key=k, field_path=f'exposure.production.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=_as_float, keep_per_db=True)
    environment_cols = FIELD_RULES['environment_cols']
    for k, cmap in environment_cols.items():
        _add_multi_observations(out_container=unified['exposure']['environment'], out_key=k, field_path=f'exposure.environment.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    patent_cols = FIELD_RULES['patent_cols']
    for k, cmap in patent_cols.items():
        _add_multi_observations(out_container=unified['exposure']['patent'], out_key=k, field_path=f'exposure.patent.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    literature_cols = FIELD_RULES['literature_cols']
    for k, cmap in literature_cols.items():
        _add_multi_observations(out_container=unified['exposure']['literature'], out_key=k, field_path=f'exposure.literature.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=_as_float, keep_per_db=True)
    reg_top_cols = FIELD_RULES['reg_top_cols']
    for k, cmap in reg_top_cols.items():
        _add_multi_observations(out_container=unified['regulatory_listings'], out_key=k, field_path=f'regulatory_listings.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    unified['regulatory_listings'].setdefault('plastchem', {'scope': [], 'global_agreements': [], 'regional_summaries': [], 'specific_regulations': []})
    plastchem_rows = [(db, m) for db, m in valid_rows if db == 'PlastChem']
    global_agreement_keys = FIELD_RULES['global_agreement_keys']
    regional_summary_keys = FIELD_RULES['regional_summary_keys']
    specific_reg_keys = FIELD_RULES['specific_reg_keys']
    scope_mea_key = FIELD_RULES['scope_mea_key']
    scope_precedent_key = FIELD_RULES['scope_precedent_key']
    for db, m in plastchem_rows:
        row = m.get('data') or {}
        if not isinstance(row, dict):
            continue
        if scope_mea_key in row and _truthy(row.get(scope_mea_key)):
            if 'global' not in unified['regulatory_listings']['plastchem']['scope']:
                unified['regulatory_listings']['plastchem']['scope'].append('global')
            unified['audit_trail'].setdefault('regulatory_listings.plastchem.scope', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=scope_mea_key, raw_value=row.get(scope_mea_key)))
        if scope_precedent_key in row and _truthy(row.get(scope_precedent_key)):
            if 'regional' not in unified['regulatory_listings']['plastchem']['scope']:
                unified['regulatory_listings']['plastchem']['scope'].append('regional')
            unified['audit_trail'].setdefault('regulatory_listings.plastchem.scope', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=scope_precedent_key, raw_value=row.get(scope_precedent_key)))
        for k in global_agreement_keys:
            if k in row and _truthy(row.get(k)):
                if k not in unified['regulatory_listings']['plastchem']['global_agreements']:
                    unified['regulatory_listings']['plastchem']['global_agreements'].append(k)
                unified['audit_trail'].setdefault('regulatory_listings.plastchem.global_agreements', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=k, raw_value=row.get(k)))
        for k in regional_summary_keys:
            if k in row and _truthy(row.get(k)):
                if k not in unified['regulatory_listings']['plastchem']['regional_summaries']:
                    unified['regulatory_listings']['plastchem']['regional_summaries'].append(k)
                unified['audit_trail'].setdefault('regulatory_listings.plastchem.regional_summaries', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=k, raw_value=row.get(k)))
        for k in specific_reg_keys:
            if k in row and _truthy(row.get(k)):
                if k not in unified['regulatory_listings']['plastchem']['specific_regulations']:
                    unified['regulatory_listings']['plastchem']['specific_regulations'].append(k)
                unified['audit_trail'].setdefault('regulatory_listings.plastchem.specific_regulations', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=k, raw_value=row.get(k)))

    def _split_semicolon_values(v: Any) -> List[str]:
        s = _norm_str(v)
        if not s:
            return []
        return [item.strip() for item in s.split(';') if item.strip()]

    def _append_unique(container: list, values: list) -> None:
        for value in values:
            if value not in container:
                container.append(value)

    def _row_value(row: dict, *keys: str) -> Any:
        for key in keys:
            if key in row:
                return row.get(key)
        return None
    plastchem_function_top_classes = FIELD_RULES['plastchem_function_top_classes']
    plastchem_function_to_top = {function: top_class for top_class, functions in plastchem_function_top_classes.items() for function in functions}
    plastchem_polymer_columns = FIELD_RULES['plastchem_polymer_columns']
    plastchem_structural_group_columns = FIELD_RULES['plastchem_structural_group_columns']
    plastchem_concern_columns = FIELD_RULES['plastchem_concern_columns']
    if plastchem_rows:
        plastchem_classification = {'functions': {'harmonized': [], 'top_classes': []}, 'upr': {}, 'polymer_context': {}, 'structural_groups': [], 'concern': {}}
        for db, m in plastchem_rows:
            row = m.get('data') or {}
            if not isinstance(row, dict):
                continue
            functions = _split_semicolon_values(_row_value(row, 'Harmonized_functions'))
            _append_unique(plastchem_classification['functions']['harmonized'], functions)
            top_classes = [plastchem_function_to_top[item] for item in functions if item in plastchem_function_to_top]
            _append_unique(plastchem_classification['functions']['top_classes'], top_classes)
            if functions:
                unified['audit_trail'].setdefault('classification.plastchem.functions.harmonized', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col='Harmonized_functions', raw_value=row.get('Harmonized_functions')))
            for key, source_col in [('use', 'Use'), ('presence', 'Presence'), ('release', 'Release')]:
                raw_value = _row_value(row, source_col)
                if _truthy(raw_value):
                    plastchem_classification['upr'][key] = True
                    unified['audit_trail'].setdefault(f'classification.plastchem.upr.{key}', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=source_col, raw_value=raw_value))
            for column in plastchem_polymer_columns:
                raw_value = _row_value(row, column)
                numeric_value = _as_float(raw_value)
                if numeric_value is None:
                    continue
                plastchem_classification['polymer_context'][column] = numeric_value
                unified['audit_trail'].setdefault('classification.plastchem.polymer_context', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=column, raw_value=raw_value))
            structural_hits = []
            for column in plastchem_structural_group_columns:
                if _truthy(_row_value(row, column)):
                    structural_hits.append(column)
            _append_unique(plastchem_classification['structural_groups'], structural_hits)
            if structural_hits:
                unified['audit_trail'].setdefault('classification.plastchem.structural_groups', []).append(_mk_audit_entry(db=db, row_index=m.get('row_index'), match_type=m.get('match_type'), match_col=m.get('match_col'), match_value=m.get('match_value'), source_col=';'.join(structural_hits), raw_value=1))
            for column in plastchem_concern_columns:
                raw_value = _row_value(row, column)
                if _is_nullish(raw_value):
                    continue
                if column.endswith('_list') or column in {'Red_list', 'Orange_list', 'Watch_list', 'White_list', 'Grey_list'}:
                    if not _truthy(raw_value):
                        continue
                plastchem_classification['concern'][column] = raw_value
        plastchem_classification = {key: value for key, value in plastchem_classification.items() if value and (not (isinstance(value, dict) and all((not item for item in value.values()))))}
        if plastchem_classification:
            unified['classification']['plastchem'] = plastchem_classification
    classification_cols = FIELD_RULES['classification_cols']
    for k, cmap in classification_cols.items():
        _add_multi_observations(out_container=unified['classification'], out_key=k, field_path=f'classification.{k}', candidates_by_db=cmap, valid_rows=valid_rows, normalizer=lambda x: x, keep_per_db=True)
    return unified
CLASSIFICATION_OUTPUT_COLUMNS = ['classification_info_json', 'classification_summary', 'function_top_classes', 'polymer_context_summary', 'structural_group_summary', 'concern_status']
POLYMER_VALUE_LABELS = {2.0: 'released', 1.0: 'present', 0.5: 'used', 0.25: 'inconclusive', 0.0: 'not_detected'}
CONCERN_LIST_PRIORITY = ['Red_list', 'Orange_list', 'Watch_list', 'White_list', 'Grey_list']

def _is_nullish(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == '':
        return True
    return False

def _json_default(o):
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    if o.__class__.__name__ == 'Timestamp':
        try:
            return o.isoformat()
        except Exception:
            return str(o)
    if hasattr(o, 'item'):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)

def _json_dumps_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), default=_json_default, allow_nan=True)

def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [item for item in value if not _is_nullish(item)]
    if _is_nullish(value):
        return []
    return [value]

def _join_values(values: list, *, limit: int | None=None) -> str | None:
    clean = [str(value).strip() for value in values if not _is_nullish(value) and str(value).strip()]
    if not clean:
        return None
    unique = list(dict.fromkeys(clean))
    if limit is not None and len(unique) > limit:
        return '; '.join(unique[:limit]) + f'; +{len(unique) - limit} more'
    return '; '.join(unique)

def _polymer_status_label(value: Any) -> str | None:
    try:
        numeric_value = float(value)
    except Exception:
        return None
    return POLYMER_VALUE_LABELS.get(numeric_value, str(value))

def _build_classification_outputs(slim_record: dict) -> dict[str, Any]:
    classification = slim_record.get('classification') or {}
    outputs = {column: None for column in CLASSIFICATION_OUTPUT_COLUMNS}
    if not classification:
        return outputs
    outputs['classification_info_json'] = _json_dumps_compact(classification)
    plastchem = classification.get('plastchem') if isinstance(classification, dict) else {}
    if not isinstance(plastchem, dict):
        plastchem = {}
    functions = plastchem.get('functions') if isinstance(plastchem.get('functions'), dict) else {}
    harmonized_functions = _as_list(functions.get('harmonized'))
    top_classes = _as_list(functions.get('top_classes'))
    outputs['function_top_classes'] = _join_values(top_classes)
    polymer_context = plastchem.get('polymer_context') if isinstance(plastchem.get('polymer_context'), dict) else {}
    polymer_parts = []
    for polymer, value in polymer_context.items():
        label = _polymer_status_label(value)
        if label and label != 'not_detected':
            polymer_parts.append(f'{polymer}:{label}')
    outputs['polymer_context_summary'] = _join_values(polymer_parts, limit=12)
    structural_groups = _as_list(plastchem.get('structural_groups'))
    outputs['structural_group_summary'] = _join_values(structural_groups, limit=12)
    concern = plastchem.get('concern') if isinstance(plastchem.get('concern'), dict) else {}
    concern_parts = []
    for key in CONCERN_LIST_PRIORITY:
        if key in concern and (not _is_nullish(concern.get(key))) and (str(concern.get(key)).strip() not in {'0', '0.0'}):
            concern_parts.append(key)
    for key in ['Hazard_score', 'Hazard_score_sum', 'priority_groups']:
        if key in concern and (not _is_nullish(concern.get(key))):
            concern_parts.append(f'{key}:{concern.get(key)}')
    outputs['concern_status'] = _join_values(concern_parts)
    summary_parts = []
    if top_classes or harmonized_functions:
        function_text = _join_values(harmonized_functions, limit=8)
        top_text = _join_values(top_classes)
        if top_text and function_text:
            summary_parts.append(f'Function: {top_text} ({function_text})')
        elif top_text:
            summary_parts.append(f'Function: {top_text}')
        elif function_text:
            summary_parts.append(f'Function: {function_text}')
    polymer_text = outputs['polymer_context_summary']
    if polymer_text:
        summary_parts.append(f'Polymer: {polymer_text}')
    structural_text = outputs['structural_group_summary']
    if structural_text:
        summary_parts.append(f'Groups: {structural_text}')
    concern_text = outputs['concern_status']
    if concern_text:
        summary_parts.append(f'Concern: {concern_text}')
    if not summary_parts:
        non_plastchem_keys = [key for key, value in classification.items() if value]
        if non_plastchem_keys:
            summary_parts.append(f'Other classification: {_join_values(non_plastchem_keys)}')
    outputs['classification_summary'] = ' | '.join(summary_parts) if summary_parts else None
    return outputs

def make_slim_record(unified: dict) -> dict:
    """
    Slim version:
      - Keep main structure
      - Keep only non-empty fields (except exposure sub-block skeleton)
      - Add identity._sources (field -> sorted list of dbs that provided observations)
      - Keep mismatch_report always
    """
    audit = unified.get('audit_trail') or {}
    identity_sources: Dict[str, List[str]] = {}
    for field_path, entries in audit.items():
        if not isinstance(field_path, str) or not field_path.startswith('identity.'):
            continue
        field = field_path.split('.', 1)[1]
        dbs = {e.get('db') for e in entries or [] if isinstance(e, dict) and e.get('db')}
        if dbs:
            identity_sources[field] = sorted(dbs)
    identity_out = dict(unified.get('identity') or {})
    if identity_sources:
        identity_out['_sources'] = identity_sources

    def _prune_dict(d: dict) -> dict:
        out = {}
        for k, v in (d or {}).items():
            if isinstance(v, dict):
                if v:
                    out[k] = v
            elif isinstance(v, list):
                if len(v) > 0:
                    out[k] = v
            elif not _is_nullish(v):
                out[k] = v
        return out
    hazard_out = _prune_dict(unified.get('hazard') or {})
    classification_out = _prune_dict(unified.get('classification') or {})
    regulatory_out = dict(unified.get('regulatory_listings') or {})
    plastchem = regulatory_out.get('plastchem') or {}
    if isinstance(plastchem, dict):
        plastchem_pruned = {}
        for k in ['scope', 'global_agreements', 'regional_summaries', 'specific_regulations']:
            if k in plastchem and isinstance(plastchem[k], list) and (len(plastchem[k]) > 0):
                plastchem_pruned[k] = plastchem[k]
        if plastchem_pruned:
            regulatory_out['plastchem'] = plastchem_pruned
        else:
            regulatory_out['plastchem'] = {'scope': [], 'global_agreements': [], 'regional_summaries': [], 'specific_regulations': []}
    regulatory_out = _prune_dict(regulatory_out)
    exposure_in = unified.get('exposure') or {}
    exposure_out = {'human': _prune_dict(exposure_in.get('human') or {}), 'migration': _prune_dict(exposure_in.get('migration') or {}), 'production': _prune_dict(exposure_in.get('production') or {}), 'environment': _prune_dict(exposure_in.get('environment') or {}), 'patent': _prune_dict(exposure_in.get('patent') or {}), 'literature': _prune_dict(exposure_in.get('literature') or {})}
    mismatch = unified.get('mismatch_report', [])
    if mismatch is None:
        mismatch = []
    slim = {'identity': identity_out, 'hazard': hazard_out, 'exposure': exposure_out, 'regulatory_listings': regulatory_out, 'classification': classification_out, 'mismatch_report': mismatch}
    return slim

def iter_audit_rows(unified: dict, *, compound_key: str, include_extracted: bool=True, include_mismatch: bool=True) -> Iterable[dict]:
    """
    Yields row-wise audit records for search / filter.
    - status: "extracted" (from audit_trail) or "mismatch" (from mismatch_report)
    """
    if include_extracted:
        audit = unified.get('audit_trail') or {}
        for field_path, entries in audit.items():
            if not isinstance(entries, list):
                continue
            for e in entries:
                if not isinstance(e, dict):
                    continue
                yield {'compound_key': compound_key, 'status': 'extracted', 'field_path': field_path, 'db': e.get('db'), 'row_index': e.get('row_index'), 'match_type': e.get('match_type'), 'match_col': e.get('match_col'), 'match_value': e.get('match_value'), 'source_col': e.get('source_col'), 'raw_value': e.get('raw_value'), 'selected': e.get('selected', None)}
    if include_mismatch:
        mismatches = unified.get('mismatch_report') or []
        for m in mismatches:
            if not isinstance(m, dict):
                continue
            yield {'compound_key': compound_key, 'status': 'mismatch', 'field_path': m.get('field_path'), 'db': m.get('db'), 'row_index': m.get('row_index'), 'match_type': m.get('match_type'), 'match_col': m.get('match_col', None), 'match_value': m.get('match_value'), 'source_col': m.get('source_col'), 'raw_value': m.get('raw_value'), 'reason': m.get('reason')}
