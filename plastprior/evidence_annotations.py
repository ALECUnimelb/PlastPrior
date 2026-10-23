"""Stage 4C analytical-platform and regulatory-list annotations with auditable associations.

Pure value/classification rules preserve the frozen implementation identified in
``evidence_annotations.json``. Identity resolution and scoring are outside this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
from typing import Any

import pandas as pd

from .inputs import DEFAULT_CATALOG, _file_hash, load_catalog, resolve_data_root
from .evidence import _json, _clean_row, _read_csv
from .evidence_specialists import require_prediction_isolation
from .lrtp import _verify_outputs

DEFAULT_POLICY = Path(__file__).with_name("evidence_annotations.json")
POLICY_HASH = _file_hash(DEFAULT_POLICY)
POLICY = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
ANALYTICAL_SOURCE_ID = POLICY["constants"]["ANALYTICAL_SOURCE_ID"]
ANALYTICAL_INTERPRETATION = POLICY["constants"]["ANALYTICAL_INTERPRETATION"]
NORMAN_SUSDAT_KEY_COLUMNS = POLICY["constants"]["NORMAN_SUSDAT_KEY_COLUMNS"]
NORMAN_ANALYTICAL_COLUMNS = POLICY["constants"]["NORMAN_ANALYTICAL_COLUMNS"]
INVENTORY_REGISTRATION_CLASS = POLICY["constants"]["INVENTORY_REGISTRATION_CLASS"]
REGULATORY_CLASS_PRIORITY = POLICY["constants"]["REGULATORY_CLASS_PRIORITY"]
REGULATORY_CLASS_LABELS = POLICY["constants"]["REGULATORY_CLASS_LABELS"]
REGULATORY_ACTION_CLASS_BY_TAG = POLICY["constants"]["REGULATORY_ACTION_CLASS_BY_TAG"]
OUTPUT_COLUMNS = POLICY["output_columns"]
REGULATORY_CLASS_SEVERITY = {name: len(REGULATORY_CLASS_PRIORITY) - i for i, name in enumerate(REGULATORY_CLASS_PRIORITY)}
_INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{8}[SN]A-[A-Z]$")
_CID_RE = re.compile(r"\d+")

def _is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_float(value: Any) -> float | None:
    if _is_nullish(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _clean_scalar(value: Any) -> Any:
    if _is_nullish(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _score_pair(primary: float | None, secondary: float | None) -> float | None:
    if primary is None or secondary is None:
        return None
    return min(primary, secondary)


def _format_platform_label(value: Any) -> str | None:
    if _is_nullish(value):
        return None
    label = str(value).strip().replace("_", " ")
    return label or None


def _detectability_summary(detectability: dict[str, Any] | None) -> str:
    if detectability is None:
        return "No NORMAN SusDat match"

    preferred = _format_platform_label(detectability.get("preferred_platform"))
    if preferred:
        return preferred

    chromatography = _format_platform_label(detectability.get("pred_chromatography"))
    ionization = _format_platform_label(detectability.get("pred_ionization_source"))
    esi_mode = _format_platform_label(detectability.get("pred_esi_mode"))
    parts = [part for part in [chromatography, ionization, esi_mode] if part]
    return " / ".join(parts) if parts else "NORMAN SusDat match; no platform prediction"


def _row_to_detectability(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None:
        return None

    prob_rplc = _as_float(row.get("Prob. RPLC"))
    prob_gc = _as_float(row.get("Prob. of GC"))
    prob_esi = _as_float(row.get("Prob. ESI"))
    prob_ei = _as_float(row.get("Prob. EI"))
    prob_pos_esi = _as_float(row.get("Prob. +ESI"))
    prob_neg_esi = _as_float(row.get("Prob. -ESI"))

    return {
        "source_db": ANALYTICAL_SOURCE_ID,
        "norman_susdat_id": _clean_scalar(row.get("Norman_SusDat_ID")),
        "name": _clean_scalar(row.get("Name")),
        "lookup_inchikey": _clean_scalar(row.get("Analytical_lookup_inchikey")),
        "preferred_platform": _clean_scalar(row.get("Preferable Platform by decision Tree")),
        "pred_chromatography": _clean_scalar(row.get("Pred. Chromatography")),
        "pred_ionization_source": _clean_scalar(row.get("Pred. Ionization source")),
        "pred_esi_mode": _clean_scalar(row.get("Pred. ESI mode")),
        "probabilities": {
            "rplc": prob_rplc,
            "gc": prob_gc,
            "esi": prob_esi,
            "ei": prob_ei,
            "positive_esi": prob_pos_esi,
            "negative_esi": prob_neg_esi,
            "both_ionization_sources": _as_float(row.get("Prob. of both Ionization Source")),
            "both_esi_modes": _as_float(row.get("Prob. both ESI mode")),
        },
        "derived_scores": {
            "lc_esi": _score_pair(prob_rplc, prob_esi),
            "gc_ei": _score_pair(prob_gc, prob_ei),
        },
        "retention_time_predictions": {
            "positive_esi": _as_float(row.get("Pred_RTI_Positive_ESI")),
            "positive_esi_uncertainty": _as_float(row.get("Uncertainty_RTI_pos")),
            "negative_esi": _as_float(row.get("Pred_RTI_Negative_ESI")),
            "negative_esi_uncertainty": _as_float(row.get("Uncertainty_RTI_neg")),
        },
    }


@dataclass
class GICLookupMatch:
    """Identifiers, SIDs, and list tags returned by one GIC lookup path."""

    method: str = "none"
    query_values: list[str] = field(default_factory=list)
    sids: list[int] = field(default_factory=list)
    list_tags: list[str] = field(default_factory=list)
    bridged_cids: dict[str, list[str]] = field(default_factory=dict)


def _normalise_inchikey(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "NULL"}:
        return None
    if not _INCHIKEY_RE.match(text):
        return None
    return text


def _normalise_cid(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    match = _CID_RE.search(text)
    if match is None:
        return None
    return f"CID{match.group(0)}"


def _parse_cids(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, float) and pd.isna(value):
        return set()
    return {f"CID{match.group(0)}" for match in _CID_RE.finditer(str(value))}


def _clean_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _derive_regulatory_action_class(
    list_tag: str,
    scope_class: str,
    explicit_class: str = "",
) -> tuple[str, str]:
    explicit = explicit_class.strip()
    if explicit:
        if explicit not in REGULATORY_CLASS_SEVERITY:
            raise ValueError(
                f"Unsupported regulatory_action_class {explicit!r} for GIC list tag {list_tag!r}."
            )
        return explicit, "metadata"
    if list_tag in REGULATORY_ACTION_CLASS_BY_TAG:
        return REGULATORY_ACTION_CLASS_BY_TAG[list_tag], "default_tag_mapping"
    if scope_class == "auxiliary":
        return "auxiliary_identifier_only", "default_auxiliary_scope"
    return "monitoring_reporting_or_hazard_classification", "fallback_unknown_non_auxiliary"


def load_gic_metadata(metadata_file: str | Path) -> dict[str, dict[str, str]]:
    """Load list-tag metadata keyed by list_tag."""
    metadata = pd.read_csv(metadata_file, dtype=str, encoding="utf-8").fillna("")
    required = {"list_tag", "regulation_name", "jurisdiction", "scope_class", "source_date"}
    missing = required.difference(metadata.columns)
    if missing:
        raise ValueError(f"GIC metadata is missing required columns: {sorted(missing)}")
    out: dict[str, dict[str, str]] = {}
    for _, row in metadata.iterrows():
        list_tag = str(row["list_tag"]).strip()
        if not list_tag:
            continue
        scope_class = str(row["scope_class"]).strip()
        action_class, class_source = _derive_regulatory_action_class(
            list_tag,
            scope_class,
            str(row.get("regulatory_action_class", "")).strip(),
        )
        severity_rank = str(row.get("severity_rank", "")).strip()
        if not severity_rank:
            severity_rank = str(REGULATORY_CLASS_SEVERITY[action_class])
        out[list_tag] = {
            "regulation_name": str(row["regulation_name"]).strip(),
            "jurisdiction": str(row["jurisdiction"]).strip(),
            "scope_class": scope_class,
            "source_date": str(row["source_date"]).strip(),
            "regulatory_action_class": action_class,
            "severity_rank": severity_rank,
            "action_label": str(row.get("action_label", "")).strip() or REGULATORY_CLASS_LABELS[action_class],
            "class_rationale": str(row.get("class_rationale", "")).strip() or class_source,
        }
    return out


def _is_auxiliary_tag(tag: str, meta: dict[str, str]) -> bool:
    action_class = meta.get("regulatory_action_class") or REGULATORY_ACTION_CLASS_BY_TAG.get(tag, "")
    return meta.get("scope_class") == "auxiliary" or action_class == "auxiliary_identifier_only"


def _list_tag_class(tag: str, meta: dict[str, str]) -> str:
    action_class = meta.get("regulatory_action_class", "").strip()
    if action_class in REGULATORY_CLASS_SEVERITY:
        return action_class
    return _derive_regulatory_action_class(tag, meta.get("scope_class", ""))[0]


def _ordered_classes(listing_records: list[dict[str, Any]], *, include_auxiliary: bool = False) -> list[str]:
    observed = set()
    for record in listing_records:
        if record["is_auxiliary"] and not include_auxiliary:
            continue
        observed.add(record["regulatory_action_class"])
    return [class_name for class_name in REGULATORY_CLASS_PRIORITY if class_name in observed]


def _primary_status(listing_records: list[dict[str, Any]]) -> str:
    regulatory_classes = _ordered_classes(listing_records)
    if regulatory_classes:
        return regulatory_classes[0]
    auxiliary_classes = _ordered_classes(listing_records, include_auxiliary=True)
    if auxiliary_classes:
        return "auxiliary_identifier_only"
    return "not_listed"


def _listing_record(tag: str, metadata: dict[str, dict[str, str]]) -> dict[str, Any]:
    meta = metadata.get(tag, {})
    action_class = _list_tag_class(tag, meta)
    is_auxiliary = _is_auxiliary_tag(tag, meta)
    try:
        severity_rank = int(meta.get("severity_rank") or REGULATORY_CLASS_SEVERITY[action_class])
    except (TypeError, ValueError):
        severity_rank = REGULATORY_CLASS_SEVERITY[action_class]
    return {
        "list_tag": tag,
        "regulation_name": meta.get("regulation_name", ""),
        "jurisdiction": meta.get("jurisdiction", ""),
        "scope_class": meta.get("scope_class", ""),
        "source_date": meta.get("source_date", ""),
        "regulatory_action_class": action_class,
        "severity_rank": severity_rank,
        "action_label": meta.get("action_label", "") or REGULATORY_CLASS_LABELS[action_class],
        "class_rationale": meta.get("class_rationale", ""),
        "is_auxiliary": is_auxiliary,
    }


def _listing_records(list_tags: list[str], metadata: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    return [_listing_record(tag, metadata) for tag in sorted(dict.fromkeys(list_tags))]


def _tags_for_sids(inventory: Any, sids: set[int]) -> list[str]:
    tags = set()
    for sid in sorted(sids):
        tags.update(str(tag) for tag in inventory.get_by_sids("list_tag", [sid]))
    return sorted(tags)


def _match_for_identifier(
    inventory: Any,
    identifier: str,
    method: str,
) -> GICLookupMatch:
    sids = {int(sid) for sid in inventory.get_by_identifiers("sid", [identifier])}
    return GICLookupMatch(
        method=method,
        query_values=[identifier],
        sids=sorted(sids),
        list_tags=_tags_for_sids(inventory, sids),
    )


def _match_for_cids(
    inventory: Any,
    cids: set[str],
    *,
    pubchemlite_cids: set[str] | None = None,
    susdat_cids: set[str] | None = None,
) -> GICLookupMatch:
    sids: set[int] = set()
    for cid in sorted(cids):
        sids.update(int(sid) for sid in inventory.get_by_identifiers("sid", [cid]))
    return GICLookupMatch(
        method="cid_bridge",
        query_values=sorted(cids),
        sids=sorted(sids),
        list_tags=_tags_for_sids(inventory, sids),
        bridged_cids={
            "pubchemlite": sorted(pubchemlite_cids or set()),
            "susdat": sorted(susdat_cids or set()),
        },
    )


def _has_regulatory_listing(match: GICLookupMatch, metadata: dict[str, dict[str, str]]) -> bool:
    return any(not _is_auxiliary_tag(tag, metadata.get(tag, {})) for tag in match.list_tags)


def _inventory_listing_fields(records: list[dict[str, Any]]) -> tuple[int, str]:
    """Return unique inventory/registration/use list count and tags."""
    tags = sorted({
        str(record.get("list_tag", "")).strip()
        for record in records
        if not record.get("is_auxiliary")
        and record.get("regulatory_action_class") == INVENTORY_REGISTRATION_CLASS
        and str(record.get("list_tag", "")).strip()
    })
    return len(tags), "; ".join(tags)


def _summarise_listing(records: list[dict[str, Any]], status: str) -> str:
    if status == "not_listed":
        return ""

    include_auxiliary = status == "auxiliary_identifier_only"
    groups = []
    for class_name in REGULATORY_CLASS_PRIORITY:
        class_records = [
            record for record in records
            if record["regulatory_action_class"] == class_name
            and (include_auxiliary or not record["is_auxiliary"])
        ]
        if not class_records:
            continue
        tags = ", ".join(record["list_tag"] for record in class_records)
        groups.append(f"{REGULATORY_CLASS_LABELS[class_name]}: {tags}")
    return "; ".join(groups)


def _match_to_audit(match: GICLookupMatch) -> dict[str, Any]:
    return {
        "method": match.method,
        "query_values": match.query_values,
        "matched_sids": match.sids,
        "matched_list_tags": match.list_tags,
        "bridged_cids": match.bridged_cids,
    }


def source_record(source, number, raw, native_id=None):
    """Use the same content-addressed row identity as source ingestion."""
    record_id = hashlib.sha256(json.dumps(
        [source['id'], source['table_id'], source['sha256'], number], separators=(',', ':')
    ).encode('utf-8')).hexdigest()
    return {'record_id': record_id, 'source_id': source['id'], 'table_id': source['table_id'],
            'source_filename': source['filename'], 'source_sha256': source['sha256'],
            'source_sheet': source.get('sheet'), 'source_record_number': number,
            'source_row_number': number + 1 if source.get('sheet') is not None else None, 'source_native_id': _clean_scalar(native_id),
            'raw_fields': _clean_row(raw)}


def build_norman_lookup(raw, source):
    """Rank all MS-ready candidates and retain the losing and unusable rows."""
    columns = NORMAN_SUSDAT_KEY_COLUMNS + NORMAN_ANALYTICAL_COLUMNS
    if set(columns) - set(raw.columns):
        raise ValueError('NORMAN analytical columns are incomplete.')
    table = raw[columns].copy()
    table['Analytical_lookup_inchikey'] = table['MS_Ready_StdInChIKey'].map(
        lambda v: None if _is_nullish(v) else str(v).strip().upper() or None)
    probability_columns = [c for c in NORMAN_ANALYTICAL_COLUMNS if c.startswith('Prob.')]
    for column in probability_columns:
        table[column] = pd.to_numeric(table[column], errors='coerce')
    table['_analytical_nonnull_count'] = table[NORMAN_ANALYTICAL_COLUMNS].notna().sum(axis=1)
    table['_analytical_best_score'] = table[['Prob. RPLC', 'Prob. of GC', 'Prob. ESI', 'Prob. EI']].max(axis=1)
    ranked = table.dropna(subset=['Analytical_lookup_inchikey']).sort_values(
        ['Analytical_lookup_inchikey', '_analytical_nonnull_count', '_analytical_best_score'],
        ascending=[True, False, False])
    chosen = ranked.drop_duplicates('Analytical_lookup_inchikey', keep='first')
    winner = dict(zip(chosen['Analytical_lookup_inchikey'], chosen.index))
    ranks = {i: rank for _, group in ranked.groupby('Analytical_lookup_inchikey') for rank, i in enumerate(group.index, 1)}
    audit, lookup = [], {}
    for i, row in table.iterrows():
        key = _clean_scalar(row['Analytical_lookup_inchikey'])
        selected = key is not None and winner.get(key) == i
        best = table.loc[winner[key]] if key in winner else None
        reason = 'selected_highest_completeness_then_probability' if selected else 'missing_ms_ready_key'
        if best is not None and not selected:
            reason = ('lower_nonmissing_field_count' if row['_analytical_nonnull_count'] < best['_analytical_nonnull_count']
                      else 'lower_maximum_platform_probability' if pd.notna(best['_analytical_best_score']) and
                      (pd.isna(row['_analytical_best_score']) or row['_analytical_best_score'] < best['_analytical_best_score'])
                      else 'ranking_tie_first_source_row_retained')
        record = source_record(source, int(i) + 1, raw.loc[i].to_dict(), row['Norman_SusDat_ID'])
        conversions = [{'column': c, 'raw_value': _clean_scalar(raw.at[i, c]),
                        'value': _clean_scalar(row[c]), 'reason': 'missing' if _is_nullish(raw.at[i, c]) else
                        'non_numeric_coerced_to_missing' if pd.isna(row[c]) else 'numeric_value'} for c in probability_columns]
        audit.append({**record, 'lookup_inchikey': key, 'selected': selected, 'decision_reason': reason,
                      'rank': ranks.get(i), 'nonnull_count': int(row['_analytical_nonnull_count']),
                      'best_probability': _clean_scalar(row['_analytical_best_score']), 'probability_conversions': conversions})
        if selected:
            lookup[key] = {'record_id': record['record_id'], 'evidence': _row_to_detectability(row)}
    return lookup, audit


def build_cid_bridges(pubchem, norman, sources, target_keys):
    """Keep source rows and every eligible key/CID edge for target compounds."""
    bridges = {'pubchemlite': defaultdict(set), 'susdat': defaultdict(set)}
    links, rows = [], []
    for kind, table, key_columns, cid_column in (
        ('pubchemlite', pubchem, ['InChIKey'], 'Related_CIDs'),
        ('susdat', norman, ['StdInChIKey', 'MS_Ready_StdInChIKey'], 'PubChem_CID')):
        for i, raw in enumerate(table.to_dict('records'), 1):
            keys = [(c, _normalise_inchikey(raw[c])) for c in key_columns]
            relevant = [(c, k) for c, k in keys if k in target_keys]
            if not relevant:
                continue
            cids = _parse_cids(raw[cid_column]) if kind == 'pubchemlite' else {_normalise_cid(raw[cid_column])} - {None}
            record = source_record(sources[kind], i, raw, raw.get('Identifier' if kind == 'pubchemlite' else 'Norman_SusDat_ID'))
            rows.append(record)
            for column, key in relevant:
                bridges[kind][key].update(cids)
                links.append({'compound_key': key, 'source_record_id': record['record_id'], 'source': kind,
                              'key_column': column, 'cid_column': cid_column, 'cids': sorted(cids),
                              'decision_reason': 'eligible_bridge' if cids else 'missing_or_unparseable_cid'})
    return bridges, links, rows


def resolve_gic(key, name, inventory, metadata, bridges, capabilities, row_index):
    """Reproduce lookup precedence without treating an association as identity confirmation."""
    key, name = _normalise_inchikey(key), _clean_name(name)
    selected, auxiliary, attempts = GICLookupMatch(), None, []
    for method in ('inchikey', 'cid_bridge', 'chemical_name'):
        if _has_regulatory_listing(selected, metadata):
            break
        if method == 'inchikey' and key and capabilities['inchikey']:
            match = _match_for_identifier(inventory, key, method)
        elif method == 'cid_bridge' and key and capabilities['cid']:
            pcl, sus = bridges['pubchemlite'].get(key, set()), bridges['susdat'].get(key, set())
            if not pcl | sus:
                continue
            match = _match_for_cids(inventory, pcl | sus, pubchemlite_cids=pcl, susdat_cids=sus)
        elif method == 'chemical_name' and name and capabilities['chemical_name']:
            match = _match_for_identifier(inventory, name, method)
        else:
            continue
        attempts.append(_match_to_audit(match))
        if _has_regulatory_listing(match, metadata):
            selected = match
        elif match.list_tags and auxiliary is None:
            auxiliary = match
    if not selected.list_tags and auxiliary is not None:
        selected = auxiliary
    listings = _listing_records(selected.list_tags, metadata)
    status = _primary_status(listings)
    classes = _ordered_classes(listings, include_auxiliary=status == 'auxiliary_identifier_only')
    regulatory_count = sum(not r['is_auxiliary'] for r in listings)
    count, tags = _inventory_listing_fields(listings)
    count = count if attempts else None
    summary = _summarise_listing(listings, status)
    data_status = 'available' if attempts else 'not_queried'
    caveats = []
    if not attempts:
        caveats.append('no_usable_gic_identifier_query')
    else:
        if selected.method == 'chemical_name': caveats.append('matched_by_chemical_name_fallback')
        if selected.method == 'cid_bridge': caveats.append('matched_by_pubchem_cid_bridge')
        if status == 'auxiliary_identifier_only': caveats.append('auxiliary_identifier_only_no_regulatory_list')
        if status == 'not_listed': caveats.append('no_gic_list_tags_found')
    fields = dict(zip(OUTPUT_COLUMNS[1:], [status, regulatory_count, '; '.join(classes), summary, count, tags, data_status]))
    audit = {'compound_key': key or name or '', 'row_index': row_index, 'inchikey': key or '', 'name': name or '',
             'status': status, 'regulatory_classes': classes, 'regulatory_listing_count': regulatory_count,
             'inventory_listing_count': count, 'inventory_list_tags': tags.split('; ') if tags else [],
             'inventory_data_status': data_status, 'summary': summary, 'match_method': selected.method,
             'query_values': selected.query_values, 'matched_sids': selected.sids, 'matched_list_tags': selected.list_tags,
             'lookup_attempts': attempts, 'listings': listings, 'bridged_cids': selected.bridged_cids, 'caveats': caveats}
    return fields, audit


def trace_gic_sources(path, used_sids, inventory):
    """Trace GIC's global identifier-tag union back to every contributing JSONL row."""
    from gic.datastructs.associated_values import AssociatedValues
    path = Path(path)
    fingerprint = _file_hash(path)
    rows, identifiers = [], set()
    with path.open(encoding='utf-8') as stream:
        dictionary = json.loads(next(stream))
        for number, line in enumerate(stream, 2):
            for sid, raw in json.loads(line).items():
                if int(sid) not in used_sids:
                    continue
                values = AssociatedValues({kind: data.keys() for kind, data in raw.items()})
                values.clean()
                effective = sorted(values.get_identifiers())
                identifiers.update(effective)
                rows.append({'source_filename': path.name, 'source_sha256': fingerprint,
                             'source_line_number': number, 'sid': int(sid), 'raw_fields': raw,
                             'effective_identifiers': effective})
    support, identifier_tags = [], defaultdict(set)
    tags = dictionary['list_data']
    with path.open(encoding='utf-8') as stream:
        next(stream)
        for number, line in enumerate(stream, 2):
            for sid, raw in json.loads(line).items():
                for kind, values in raw.items():
                    for identifier, ids in values.items():
                        if identifier not in identifiers:
                            continue
                        label_tags = [tags[str(i)] for i in ids]
                        identifier_tags[identifier].update(label_tags)
                        support.append({'source_filename': path.name, 'source_sha256': fingerprint,
                                        'source_line_number': number, 'sid': int(sid), 'identifier_field': kind,
                                        'identifier': identifier, 'list_ids': ids, 'list_tags': label_tags})
    for row in rows:
        local = {tags[str(i)] for values in row['raw_fields'].values() for ids in values.values() for i in ids}
        effective = set().union(*(identifier_tags[value] for value in row['effective_identifiers']))
        if sorted(effective) != inventory.get_by_sids('list_tag', [row['sid']]):
            raise ValueError('GIC identifier-tag trace does not reproduce the pinned library.')
        row.update(local_list_tags=sorted(local), effective_list_tags=sorted(effective),
                   shared_identifier_added_tags=sorted(effective - local))
    return dictionary, rows, support


def dependency_fingerprint():
    """Reject a same-named unrelated package; pin the verified GIC query implementation."""
    import gic
    dep = POLICY['gic_dependency']
    dist = importlib.metadata.distribution('gic')
    origin = json.loads(dist.read_text('direct_url.json') or '{}')
    if dist.version != dep['version'] or (origin.get('vcs_info') and (origin.get('url') != dep['url'] or origin['vcs_info'].get('commit_id') != dep['commit'])):
        raise ValueError('Install the GIC repository revision declared in requirements.txt; PyPI gic is a different project.')
    root = Path(gic.__file__).parent
    # Normalise line endings so a Windows Git checkout can reproduce the same code.
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
             for p in sorted(root.rglob('*.py'))}
    fingerprint = hashlib.sha256(_json(files).encode('utf-8')).hexdigest()
    if fingerprint != dep['source_sha256']:
        raise ValueError('Installed GIC implementation differs from the pinned query implementation.')
    return {'version': dist.version, 'commit': dep['commit'], 'source_sha256': fingerprint, 'installed_vcs_origin_recorded': bool(origin.get('vcs_info'))}


@dataclass
class AnnotationResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    anomalies: pd.DataFrame
    audits: dict
    manifest: dict

    def write_reports(self, output_dir):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in [('compound_annotated_evidence', self.compounds), ('annotation_historical', self.historical),
                            ('identity_review_annotations', self.anomalies)]:
            path = folder / (name + '.csv')
            frame.to_csv(path, index=False, encoding='utf-8', lineterminator='\n')
            outputs[path.name] = _file_hash(path)
        for name, records in self.audits.items():
            path = folder / (name + '.jsonl')
            with path.open('w', encoding='utf-8', newline='\n') as stream:
                for record in records: stream.write(_json(record) + '\n')
            outputs[path.name] = _file_hash(path)
        (folder / 'annotation_manifest.json').write_text(json.dumps({**self.manifest, 'output_sha256': outputs}, indent=2) + '\n', encoding='utf-8')


def integrate_annotations(specialist_results, data_root='data'):
    """Read fixed local sources and attach traceable annotations without scoring."""
    from gic import Inventory
    folder, root = Path(specialist_results), resolve_data_root(data_root)
    if POLICY['schema_version'] != 1 or _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError('Annotation policy changed; restart the process.')
    dependency = dependency_fingerprint()
    upstream_path = folder / 'specialist_manifest.json'
    upstream_hash = _file_hash(upstream_path)
    upstream = json.loads(upstream_path.read_text(encoding='utf-8'))
    _verify_outputs(folder, upstream)
    if upstream['catalog_sha256'] != _file_hash(DEFAULT_CATALOG):
        raise ValueError('Source catalog differs from Stage 4B.')
    paths = {r['role']: root.joinpath(*r['parts']) for r in POLICY['inputs']}
    for item in POLICY['inputs']:
        if _file_hash(paths[item['role']]) != item['sha256']:
            raise ValueError('Annotation source fingerprint mismatch: ' + item['role'])
    compounds = _read_csv(folder / 'compound_specialist_evidence.csv')
    if compounds['inchikey'].duplicated().any(): raise ValueError('Duplicate compound identities in Stage 4B.')
    require_prediction_isolation(compounds)
    catalog = {s['id']: s for s in load_catalog()['sources']}
    sources = {}
    for role, source_id in [('susdat', 'NORMAN_SusDat'), ('pubchemlite', 'PubChemLite')]:
        item = catalog[source_id]
        spec = item['tables'][0]
        path = paths['norman' if role == 'susdat' else role]
        if path.name != item['filename']: raise ValueError('Catalog and annotation filenames differ.')
        sources[role] = {'id': source_id, 'table_id': spec['id'], 'filename': path.name, 'sheet': spec['sheet'], 'sha256': _file_hash(path)}
    norman_columns = list(dict.fromkeys(NORMAN_SUSDAT_KEY_COLUMNS + NORMAN_ANALYTICAL_COLUMNS + ['StdInChIKey', 'PubChem_CID']))
    norman = pd.read_excel(paths['norman'], sheet_name=sources['susdat']['sheet'], usecols=norman_columns)
    pubchem = pd.read_csv(paths['pubchemlite'], usecols=['Identifier', 'InChIKey', 'Related_CIDs'], dtype='string', encoding='utf-8')
    lookup, candidates = build_norman_lookup(norman, sources['susdat'])
    bridges, bridge_links, bridge_rows = build_cid_bridges(pubchem, norman, sources, set(compounds['inchikey']))
    metadata = load_gic_metadata(paths['metadata'])
    raw_metadata = pd.read_csv(paths['metadata'], dtype=str, keep_default_na=False, encoding='utf-8')
    if raw_metadata['list_tag'].duplicated().any(): raise ValueError('Duplicate metadata list tags.')
    inventory = Inventory(str(paths['inventory']))
    capabilities = {kind: bool(inventory.get_identifiers(kind)) for kind in ['inchikey', 'cid', 'chemical_name']}
    if not any(capabilities.values()): raise ValueError('GIC inventory has no queryable identifiers.')
    gic_audit, norman_audit, decisions, records = [], [], [], []
    bridge_index = defaultdict(list)
    for link in bridge_links: bridge_index[link['compound_key']].append(link)
    used_sids = set()
    for index, row in enumerate(compounds.to_dict('records')):
        key = row['inchikey']
        match = lookup.get(key)
        payload = json.loads(row['db_extract_info'])
        if match: payload['analytical_detectability'] = match['evidence']
        norman_audit.append({'compound_key': key, 'query_value': key, 'match_method': 'exact_full_key_to_ms_ready' if match else 'none',
                             'source_record_id': match['record_id'] if match else None,
                             'decision_reason': 'selected_ranked_source_row' if match else 'no_ms_ready_key_match'})
        fields, audit = resolve_gic(key, row['name_resolved'], inventory, metadata, bridges, capabilities, index)
        gic_audit.append(audit)
        for attempt in audit['lookup_attempts']:
            used_sids.update(attempt['matched_sids'])
            chosen = attempt['method'] == audit['match_method']
            reason = ('selected_first_non_auxiliary_match' if any(not r['is_auxiliary'] for r in audit['listings']) else 'selected_auxiliary_fallback') if chosen else (
                'no_inventory_match' if not attempt['matched_sids'] else 'no_list_tags' if not attempt['matched_list_tags'] else 'auxiliary_match_superseded')
            decisions.append({'compound_key': key, **attempt, 'selected': chosen, 'decision_reason': reason,
                              'cid_source_record_ids': sorted({x['source_record_id'] for x in bridge_index[key] if x['cids']}) if attempt['method']=='cid_bridge' else [],
                              'name_source': 'Stage 2 name_resolved; compound_memberships.csv links all original source records' if attempt['method']=='chemical_name' else None,
                              'name_review_required': attempt['method']=='chemical_name' and chosen})
        records.append({**row, 'db_extract_info': _json(payload), 'Analytical_detectability': _detectability_summary(match['evidence'] if match else None),
                        **fields, 'norman_prediction_available': match is not None, 'gic_match_method': audit['match_method'],
                        'gic_name_review_required': audit['match_method']=='chemical_name',
                        'gic_multiple_cids': len(audit['query_values']) > 1 if audit['match_method']=='cid_bridge' else False,
                        'gic_multiple_sids': len(audit['matched_sids']) > 1, 'gic_metadata_historical_hash_available': False})
    tag_dictionary, inventory_rows, identifier_sources = trace_gic_sources(paths['inventory'], used_sids, inventory)
    local_tags = {row['sid']: set(row['local_list_tags']) for row in inventory_rows}
    for record, audit in zip(records, gic_audit):
        local = set().union(*(local_tags[sid] for sid in audit['matched_sids']))
        record['gic_shared_identifier_tag_expansion'] = bool(set(audit['matched_list_tags']) - local)
    for decision in decisions:
        local = set().union(*(local_tags[sid] for sid in decision['matched_sids']))
        decision['shared_identifier_added_tags'] = sorted(set(decision['matched_list_tags']) - local)
    result = pd.DataFrame(records)
    require_prediction_isolation(result)
    historical = result[['inchikey', 'db_extract_info'] + OUTPUT_COLUMNS].copy()
    anomalies = result.loc[result['qsar_identity_status'].eq('review_required'),
        ['inchikey', 'qsar_inchikey', 'vega_row_no', 'qsar_identity_reason', 'qsar_evidence_available', 'lrtp_available',
         'norman_prediction_available', 'gic_match_method', 'gic_name_review_required', 'gic_multiple_cids', 'gic_multiple_sids',
         'gic_shared_identifier_tag_expansion']].copy()
    anomalies['prediction_exclusion_reason'] = 'identity_review_required'
    stage2 = folder.parent.parent / 'stage2'
    identity_manifest = json.loads((stage2 / 'identity_manifest.json').read_text(encoding='utf-8'))
    if _file_hash(stage2 / 'identity_manifest.json') != upstream['upstream_manifest_sha256']['identity']:
        raise ValueError('Stage 4B identity run differs from the available source records.')
    _verify_outputs(stage2, identity_manifest)
    members = _read_csv(stage2 / 'compound_memberships.csv')
    review_links = members.loc[members['inchikey'].isin(anomalies['inchikey'])].to_dict('records')
    metadata_audit = [{'source_filename': paths['metadata'].name, 'source_sha256': _file_hash(paths['metadata']),
                       'source_row_number': i + 2, 'historical_file_hash_available': False, 'raw_fields': row,
                       'effective_listing': _listing_record(row['list_tag'], metadata)} for i, row in enumerate(raw_metadata.to_dict('records'))]
    if _file_hash(upstream_path) != upstream_hash: raise ValueError('Upstream manifest changed during annotation.')
    _verify_outputs(folder, upstream)
    for item in POLICY['inputs']:
        if _file_hash(paths[item['role']]) != item['sha256']: raise ValueError('Annotation input changed during integration.')
    if _file_hash(DEFAULT_POLICY) != POLICY_HASH: raise ValueError('Annotation policy changed during integration.')
    counts = {'compounds': len(result), 'norman_matched': sum(result['norman_prediction_available']),
              'gic_matched': sum(r['regulatory_listing_count'] > 0 for r in gic_audit),
              'gic_name_review_required': sum(result['gic_name_review_required']),
              'gic_tag_expansion_review_required': sum(result['gic_shared_identifier_tag_expansion']),
              'identity_review_compounds': len(anomalies), 'identity_review_source_links': len(review_links)}
    manifest = {'schema_version': 1, 'scope': POLICY['scope'], 'policy_sha256': POLICY_HASH,
                'implementation_sha256': _file_hash(Path(__file__)), 'catalog_sha256': _file_hash(DEFAULT_CATALOG),
                'upstream_manifest_sha256': upstream_hash, 'inputs': POLICY['inputs'], 'counts': counts,
                'gic_match_methods': dict(Counter(r['match_method'] for r in gic_audit)), 'gic_query_capabilities': capabilities,
                'gic_inventory_tag_dictionary': tag_dictionary, 'limitations': POLICY['limitations'],
                'dependency': dependency, 'runtime': {'python': platform.python_version(), 'pandas': pd.__version__}}
    audits = {'norman_candidates': candidates, 'norman_resolution_audit': norman_audit, 'cid_bridge_links': bridge_links,
              'cid_bridge_source_rows': bridge_rows, 'gic_resolution_audit': gic_audit, 'gic_match_decisions': decisions,
              'gic_source_rows': inventory_rows, 'gic_identifier_tag_sources': identifier_sources, 'gic_metadata_audit': metadata_audit, 'identity_review_source_links': review_links}
    return AnnotationResult(result, historical, anomalies, audits, manifest)
