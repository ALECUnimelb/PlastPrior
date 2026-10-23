"""Stage 4B literature associations and human-detection evidence with source provenance."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
import re
from typing import Any
import warnings

import pandas as pd

from .inputs import DEFAULT_CATALOG, _file_hash, load_catalog, resolve_data_root
from .identity import _valid_cas_values
from .evidence import _clean_row, _json, _read_csv
from .lrtp import _verify_outputs, VALUE_COLUMNS

DEFAULT_POLICY = Path(__file__).with_name("evidence_specialists.json")
POLICY_HASH = _file_hash(DEFAULT_POLICY)
POLICY = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
LIT_POLICY = POLICY["policies"]["litchemplast"]
FC_POLICY = POLICY["policies"]["fcchumon"]
INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
CASRN_PATTERN = re.compile(r"(?<!\d)([1-9]\d{1,6}-\d{2}-\d)(?!\d)")
S1_DETECTION_COLUMN = POLICY["fcchumon_fields"]["s1"]
S2_DETECTION_COLUMN = POLICY["fcchumon_fields"]["s2"]
S2_DATABASE_DETECTION_COLUMN = POLICY["fcchumon_fields"]["s2_database"]


def is_valid_casrn(value):
    text = str(value or "").strip()
    return text in _valid_cas_values(text)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_inchikey(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip().upper()
    return text if INCHIKEY_PATTERN.fullmatch(text) else None


def _extract_casrns(value: Any) -> tuple[str, ...]:
    if _is_missing(value):
        return ()
    return tuple(
        dict.fromkeys(
            casrn
            for casrn in CASRN_PATTERN.findall(str(value))
            if is_valid_casrn(casrn)
        )
    )


def _require_columns(table: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = sorted(set(columns) - set(table.columns))
    if missing:
        raise KeyError(f"{name} is missing required columns: {missing}")


def _target_cas_values(row: pd.Series) -> tuple[str, ...]:
    raw_values = row.get("cas_values_json")
    if isinstance(raw_values, str) and raw_values.strip():
        try:
            parsed = json.loads(raw_values)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            values = tuple(
                dict.fromkeys(
                    casrn
                    for value in parsed
                    for casrn in _extract_casrns(value)
                )
            )
            if values:
                return values
    return _extract_casrns(row.get("CAS"))


def _stringify_ids(values: pd.Series) -> str:
    cleaned = []
    for value in values.dropna().tolist():
        if isinstance(value, float) and value.is_integer():
            cleaned.append(str(int(value)))
        else:
            cleaned.append(str(value))
    return "|".join(sorted(set(cleaned)))


def _build_group_table(
    chemical_rows: pd.DataFrame,
    links: pd.DataFrame | None,
    group_column: str,
) -> pd.DataFrame:
    grouped = chemical_rows.groupby(group_column, dropna=True).agg(
        raw_chemical_row_count=("Chem_id", "size"),
        chem_id_count=("Chem_id", "nunique"),
        chem_ids=("Chem_id", _stringify_ids),
        declared_count_max=("_declared_count", "max"),
        declared_count_sum=("_declared_count", "sum"),
    )
    grouped["declared_count_max"] = grouped["declared_count_max"].fillna(0).astype(int)
    grouped["declared_count_sum"] = grouped["declared_count_sum"].fillna(0).astype(int)

    if links is None:
        grouped["linked_record_count"] = grouped["declared_count_max"]
        grouped["unique_publication_count"] = pd.NA
        grouped["count_source"] = "Chemical.count_LitChem_id_fallback"
        return grouped.reset_index()

    enriched = links.merge(
        chemical_rows[["Chem_id", group_column]],
        on="Chem_id",
        how="inner",
        validate="many_to_many",
    )
    link_stats = enriched.groupby(group_column, dropna=True).agg(
        linked_record_count=("LitChem_id", "nunique"),
        unique_publication_count=("Lit_id", "nunique"),
    )
    grouped = grouped.join(link_stats, how="left")
    grouped["linked_record_count"] = grouped["linked_record_count"].fillna(0).astype(int)
    grouped["unique_publication_count"] = (
        grouped["unique_publication_count"].fillna(0).astype(int)
    )
    grouped["count_source"] = "unique_LiteratureChemical.LitChem_id"
    return grouped.reset_index()


def build_litchemplast_indexes(
    chemical_table: pd.DataFrame,
    literature_chemical_table: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Build exact-key and missing-key CAS indexes from the raw workbook sheets."""
    _require_columns(
        chemical_table,
        ["Chem_id", "INCHIKEY", "CASRN", "count_LitChem_id"],
        "LitChemPlast Chemical",
    )
    chemical = chemical_table.copy()
    chemical["_inchikey"] = chemical["INCHIKEY"].map(_normalize_inchikey)
    chemical["_cas_values"] = chemical["CASRN"].map(_extract_casrns)
    chemical["_declared_count"] = pd.to_numeric(
        chemical["count_LitChem_id"], errors="coerce"
    ).fillna(0)
    if chemical["_declared_count"].lt(0).any():
        raise ValueError("LitChemPlast declared counts must be non-negative.")

    links: pd.DataFrame | None = None
    if literature_chemical_table is not None:
        _require_columns(
            literature_chemical_table,
            ["Chem_id", "LitChem_id", "Lit_id"],
            "LitChemPlast LiteratureChemical",
        )
        links = literature_chemical_table.loc[
            :, ["Chem_id", "LitChem_id", "Lit_id"]
        ].copy()

    exact_rows = chemical.loc[chemical["_inchikey"].notna()].copy()
    exact_groups = _build_group_table(exact_rows, links, "_inchikey")
    exact_index = {
        str(row["_inchikey"]): {
            key: row[key]
            for key in exact_groups.columns
            if key != "_inchikey"
        }
        for row in exact_groups.to_dict(orient="records")
    }

    missing_key_rows = chemical.loc[chemical["_inchikey"].isna()].copy()
    missing_key_rows = missing_key_rows.explode("_cas_values")
    missing_key_rows = missing_key_rows.loc[
        missing_key_rows["_cas_values"].notna()
    ].copy()
    cas_groups = _build_group_table(missing_key_rows, links, "_cas_values")
    cas_index = {
        str(row["_cas_values"]): {
            key: row[key]
            for key in cas_groups.columns
            if key != "_cas_values"
        }
        for row in cas_groups.to_dict(orient="records")
    }

    declared_disagreements = sum(
        int(record["linked_record_count"]) != int(record["declared_count_max"])
        for record in [*exact_index.values(), *cas_index.values()]
        if record["count_source"] == "unique_LiteratureChemical.LitChem_id"
    )
    return {
        "exact_index": exact_index,
        "missing_key_cas_index": cas_index,
        "summary": {
            "policy_version": LIT_POLICY,
            "chemical_rows": int(len(chemical_table)),
            "literature_chemical_rows": (
                int(len(literature_chemical_table))
                if literature_chemical_table is not None
                else None
            ),
            "exact_key_count": int(len(exact_index)),
            "missing_key_cas_count": int(len(cas_index)),
            "linked_vs_declared_max_disagreement_count": int(declared_disagreements),
            "count_source": (
                "unique_LiteratureChemical.LitChem_id"
                if literature_chemical_table is not None
                else "Chemical.count_LitChem_id_fallback"
            ),
        },
    }


def resolve_litchemplast_for_row(
    row: pd.Series,
    indexes: dict[str, Any],
) -> dict[str, Any]:
    """Resolve one count with exact full InChIKey precedence and guarded CAS fallback."""
    target_key = _normalize_inchikey(row.get("Inchikey_std"))
    exact_index = indexes["exact_index"]
    cas_index = indexes["missing_key_cas_index"]

    selected: dict[str, Any] | None = None
    match_method = "no_match"
    matched_identifier: str | None = None
    caveats: list[str] = []
    if target_key and target_key in exact_index:
        selected = exact_index[target_key]
        match_method = "exact_full_inchikey"
        matched_identifier = target_key
    else:
        mapping_status = str(row.get("cas_mapping_status") or "").strip()
        cas_values = _target_cas_values(row)
        candidates = [(casrn, cas_index[casrn]) for casrn in cas_values if casrn in cas_index]
        if mapping_status != "one_to_one" and candidates:
            match_method = "cas_rejected_ambiguous_target_mapping"
            caveats.append(f"cas_mapping_status={mapping_status or 'missing'}")
        elif len(candidates) == 1:
            matched_identifier, selected = candidates[0]
            match_method = "cas_fallback_source_inchikey_missing"
        elif len(candidates) > 1:
            match_method = "cas_rejected_multiple_source_candidates"
            caveats.append("multiple_missing-key LitChemPlast CAS candidates")

    count = int(selected["linked_record_count"]) if selected is not None else 0
    resolution = {
        "policy_version": LIT_POLICY,
        "target_inchikey": target_key,
        "match_method": match_method,
        "matched_identifier": matched_identifier,
        "selected": selected is not None,
        "linked_record_count": count,
        "unique_publication_count": (
            int(selected["unique_publication_count"])
            if selected is not None and not _is_missing(selected["unique_publication_count"])
            else None
        ),
        "count_source": selected.get("count_source") if selected is not None else None,
        "raw_chemical_row_count": (
            int(selected["raw_chemical_row_count"]) if selected is not None else 0
        ),
        "chem_id_count": int(selected["chem_id_count"]) if selected is not None else 0,
        "chem_ids": selected.get("chem_ids") if selected is not None else None,
        "declared_count_max": (
            int(selected["declared_count_max"]) if selected is not None else None
        ),
        "caveats": caveats,
    }
    return resolution


def _nonnegative_int(value: Any) -> int:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return 0
    if float(number) < 0:
        raise ValueError("FCChumon evidence counts must be non-negative.")
    return int(number)


def _build_sheet_index(
    table: pd.DataFrame,
    *,
    source_sheet: str,
    detection_column: str,
) -> dict[str, dict[str, Any]]:
    _require_columns(table, ["CAS", "Chemical name", detection_column], source_sheet)
    working = table.copy()
    working["_cas_values"] = working["CAS"].map(_extract_casrns)
    working["_detection_count"] = working[detection_column].map(_nonnegative_int)
    if source_sheet == "FCChumon_S2":
        _require_columns(working, [S2_DATABASE_DETECTION_COLUMN], source_sheet)
        working["_database_detection_count"] = working[
            S2_DATABASE_DETECTION_COLUMN
        ].map(_nonnegative_int)
    else:
        working["_database_detection_count"] = working["_detection_count"]
    working = working.explode("_cas_values")
    working = working.loc[working["_cas_values"].notna()].copy()

    index: dict[str, dict[str, Any]] = {}
    for casrn, group in working.groupby("_cas_values", sort=True):
        names = sorted(
            {
                str(value).strip()
                for value in group["Chemical name"].dropna().tolist()
                if str(value).strip()
            }
        )
        detection_count = int(group["_detection_count"].max())
        database_detection_count = int(group["_database_detection_count"].max())
        index[str(casrn)] = {
            "source_sheet": source_sheet,
            "source_row_count": int(len(group)),
            "chemical_names": names,
            "detection_count": detection_count,
            "database_detection_count": database_detection_count,
            "detected": detection_count > 0,
            "detection_field": detection_column,
        }
    return index


def build_fcchumon_indexes(
    s1_table: pd.DataFrame,
    s2_table: pd.DataFrame,
) -> dict[str, Any]:
    """Build CAS indexes while preserving the two source-table definitions."""
    s1_index = _build_sheet_index(
        s1_table,
        source_sheet="FCChumon_S1",
        detection_column=S1_DETECTION_COLUMN,
    )
    s2_index = _build_sheet_index(
        s2_table,
        source_sheet="FCChumon_S2",
        detection_column=S2_DETECTION_COLUMN,
    )
    overlap = sorted(set(s1_index) & set(s2_index))
    return {
        "FCChumon_S1": s1_index,
        "FCChumon_S2": s2_index,
        "summary": {
            "policy_version": FC_POLICY,
            "s1_source_rows": int(len(s1_table)),
            "s2_source_rows": int(len(s2_table)),
            "s1_valid_cas_count": int(len(s1_index)),
            "s2_valid_cas_count": int(len(s2_index)),
            "s1_detected_cas_count": int(
                sum(record["detected"] for record in s1_index.values())
            ),
            "s2_detected_cas_count": int(
                sum(record["detected"] for record in s2_index.values())
            ),
            "cross_sheet_cas_overlap_count": int(len(overlap)),
        },
    }


def resolve_fcchumon_for_row(row: pd.Series, indexes: dict[str, Any]) -> dict[str, Any]:
    """Resolve at most one FCChumon row through an unambiguous target CAS."""
    target_cas = _target_cas_values(row)
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    for casrn in target_cas:
        for sheet in ("FCChumon_S1", "FCChumon_S2"):
            record = indexes[sheet].get(casrn)
            if record is not None:
                candidates.append((sheet, casrn, record))

    mapping_status = str(row.get("cas_mapping_status") or "").strip()
    selected: tuple[str, str, dict[str, Any]] | None = None
    caveats: list[str] = []
    if not candidates:
        match_method = "no_match"
    elif mapping_status != "one_to_one":
        match_method = "cas_rejected_ambiguous_target_mapping"
        caveats.append(f"cas_mapping_status={mapping_status or 'missing'}")
    elif len(candidates) > 1:
        match_method = "cas_rejected_multiple_source_candidates"
        caveats.append("multiple FCChumon records matched target CAS aliases")
    else:
        selected = candidates[0]
        match_method = "exact_one_to_one_cas"

    source_sheet = selected[0] if selected else None
    matched_cas = selected[1] if selected else None
    source_record = selected[2] if selected else None
    detected = bool(source_record and source_record["detected"])
    return {
        "policy_version": FC_POLICY,
        "target_cas_values": list(target_cas),
        "target_cas_mapping_status": mapping_status or None,
        "match_method": match_method,
        "matched_cas": matched_cas,
        "source_sheet": source_sheet,
        "selected": source_record is not None,
        "detected": detected,
        "detection_count": (
            int(source_record["detection_count"]) if source_record is not None else 0
        ),
        "database_detection_count": (
            int(source_record["database_detection_count"])
            if source_record is not None
            else 0
        ),
        "detection_field": (
            source_record.get("detection_field") if source_record is not None else None
        ),
        "source_row_count": (
            int(source_record["source_row_count"]) if source_record is not None else 0
        ),
        "chemical_names": (
            source_record.get("chemical_names", []) if source_record is not None else []
        ),
        "caveats": caveats,
    }


def build_cas_view(compounds, members, records, cas_audit):
    """Project existing identity evidence; never resolve or merge a new identity."""
    joined = members.merge(records[["record_id", "cas_reported", "source_sha256"]],
                           on="record_id", how="left", validate="one_to_one")
    if joined["cas_reported"].isna().any():
        raise ValueError("A compound member has no source record.")
    details = {}
    for row in cas_audit.to_dict("records"):
        details[row["cas"]] = {
            "cas": row["cas"], "mapping_status": row["mapping_status"],
            "inchikey_count": int(row["inchikey_count"]), "connectivity_count": int(row["connectivity_count"]),
            "inchikeys": json.loads(row["inchikeys_json"]), "inchikey14s": json.loads(row["connectivity_keys_json"])}
    aliases, links = defaultdict(set), []
    for row in joined.to_dict("records"):
        values = _valid_cas_values(row["cas_reported"])
        aliases[row["inchikey"]].update(values)
        for cas in values or ("",):
            if cas and (cas not in details or row["inchikey"] not in details[cas]["inchikeys"]):
                raise ValueError("Member CAS differs from the Stage 2 mapping audit.")
            links.append({"inchikey": row["inchikey"], "record_id": row["record_id"],
                          "source_sha256": row["source_sha256"], "cas_reported": row["cas_reported"],
                          "cas": cas, "status": "retained_valid_alias" if cas else "no_valid_cas"})
    severity = {"one_to_one": 0, "same_connectivity_multiple_full_inchikeys": 1, "multiple_connectivity_conflict": 2}
    rows = []
    for row in compounds.to_dict("records"):
        values = sorted(aliases[row["inchikey"]])
        entries = [details[v] for v in values]
        status = max((e["mapping_status"] for e in entries), key=severity.get) if entries else "invalid_or_missing"
        rows.append({"inchikey": row["inchikey"], "CAS": row["cas_reported"],
                     "cas_values_json": _json(values), "cas_mapping_status": status,
                     "cas_mapping_count": len({k for e in entries for k in e["inchikeys"]}),
                     "cas_connectivity_count": len({k for e in entries for k in e["inchikey14s"]}),
                     "cas_mapping_details_json": _json(entries)})
    return pd.DataFrame(rows), pd.DataFrame(links)


def _load_specialist_tables(data_root, records, expected_sources):
    declarations = {t["id"]: (s, t) for s in load_catalog()["sources"] for t in s["tables"]}
    tables, source_rows, metadata = {}, [], []
    identities = records.set_index(["table_id", "source_record_number"])
    for table_id, spec in POLICY["tables"].items():
        source, table = declarations[table_id]
        path = resolve_data_root(data_root) / "SourceDatabase" / source["filename"]
        digest = _file_hash(path)
        if digest != expected_sources[path.name]:
            raise ValueError(f"Specialist source differs from Stage 4A: {path.name}")
        with warnings.catch_warnings(record=True) as notes:
            warnings.simplefilter("always")
            frame = pd.read_excel(path, sheet_name=table["sheet"], header=table["header"],
                                  engine="xlrd" if path.suffix.lower() == ".xls" else "openpyxl")
        _require_columns(frame, spec["columns"], table_id)
        if frame.columns.duplicated().any() or _file_hash(path) != digest:
            raise ValueError("Source changed during reading or has duplicate column labels.")
        native = {"litchemplast": "Chem_id", "litchemplast_links": "LitChem_id"}.get(table_id)
        for i, raw in enumerate(frame.to_dict("records"), 1):
            if table_id != "litchemplast_links":
                original = identities.loc[(table_id, str(i))]
                rid = original["record_id"]
                native_id = original["source_native_id"]
                if original["source_sha256"] != digest:
                    raise ValueError("Specialist row has inconsistent Stage 2 provenance.")
            else:
                rid = hashlib.sha256(json.dumps([source["id"], table_id, digest, i], separators=(",", ":")).encode("utf-8")).hexdigest()
                native_id = "" if _is_missing(raw[native]) else str(raw[native])
            source_rows.append({"record_id": rid, "source_id": source["id"], "table_id": table_id, "source_filename": path.name,
                                "source_sha256": digest, "source_sheet": table["sheet"],
                                "source_record_number": i, "source_row_number": i + table["header"] + 1,
                                "source_native_id": native_id, "raw_fields": _clean_row(pd.Series(raw))})
        tables[table_id] = frame
        metadata.append({"table_id": table_id, "filename": path.name, "sha256": digest,
                         "sheet": table["sheet"], "header": table["header"], "rows": len(frame),
                         "reader_warnings": "; ".join(dict.fromkeys(str(n.message) for n in notes))})
    return tables, source_rows, metadata


def _conversion_audit(source_rows):
    rows = []
    for source in source_rows:
        table = source["table_id"]
        columns = (["count_LitChem_id"] if table == "litchemplast" else
                   [S1_DETECTION_COLUMN] if table == "fcchumon_s1" else
                   [S2_DETECTION_COLUMN, S2_DATABASE_DETECTION_COLUMN] if table == "fcchumon_s2" else [])
        for col in columns:
            raw = source["raw_fields"][col]
            number = pd.to_numeric(pd.Series([raw]), errors="coerce").iloc[0]
            reason = "preserved_numeric_value"
            if pd.isna(number):
                reason = "missing_to_zero_historical_rule" if raw is None else "nonnumeric_to_zero_historical_rule"
                number = 0
            if number < 0:
                raise ValueError("Specialist evidence counts must be non-negative.")
            if table != "litchemplast":
                if int(number) != number:
                    reason = "fractional_value_truncated_historical_rule"
                number = int(number)
            rows.append({"record_id": source["record_id"], "table_id": table, "source_column": col,
                         "raw_value": raw, "normalized_value": number, "conversion_reason": reason,
                         "aggregation_rule": "maximum_and_sum_then_integer_conversion" if table == "litchemplast" else "maximum_within_sheet_and_cas"})
    return rows


def _trace_indexes(tables, source_rows):
    by_table = defaultdict(list)
    for row in source_rows:
        by_table[row["table_id"]].append(row)
    exact, missing, all_cas, fc, relationships = (defaultdict(list) for _ in range(5))
    for row in by_table["litchemplast"]:
        raw = row["raw_fields"]
        key = _normalize_inchikey(raw["INCHIKEY"])
        if key:
            exact[key].append(row)
        for cas in _extract_casrns(raw["CASRN"]):
            all_cas[cas].append(row)
            if key is None:
                missing[cas].append(row)
    for table in ("fcchumon_s1", "fcchumon_s2"):
        for row in by_table[table]:
            for cas in _extract_casrns(row["raw_fields"]["CAS"]):
                fc[table, cas].append(row)
    for row in by_table["litchemplast_links"]:
        chem_id = row["raw_fields"]["Chem_id"]
        if chem_id is not None:
            relationships[chem_id].append(row)
    chemical_ids = {row["raw_fields"]["Chem_id"] for row in by_table["litchemplast"]}
    for row in by_table["litchemplast_links"]:
        row["chemical_reference_status"] = "chemical_id_present" if row["raw_fields"]["Chem_id"] in chemical_ids else "orphan_or_missing_chemical_id"
    return exact, missing, all_cas, fc, relationships


def _candidate_trace(key, cas_values, lit, human, indexes):
    exact, missing, all_cas, fc, relationships = indexes
    candidates, link_decisions = [], []

    def add(kind, identifier, source, selected, reason):
        relation_rows = {r["record_id"]: r for s in source
                         for r in relationships.get(s["raw_fields"].get("Chem_id"), [])} if kind.startswith("lit_") else {}
        candidates.append({"compound_key": key, "candidate_type": kind, "identifier": identifier,
                           "selected": selected, "selection_reason": reason,
                           "source_record_ids": [s["record_id"] for s in source],
                           "relationship_record_ids": sorted(relation_rows)})
        if kind in {"fcchumon_s1", "fcchumon_s2"}:
            columns = [S1_DETECTION_COLUMN] if kind == "fcchumon_s1" else [S2_DETECTION_COLUMN, S2_DATABASE_DETECTION_COLUMN]
            decisions = []
            for column in columns:
                values = [_nonnegative_int(s["raw_fields"][column]) for s in source]
                maximum = max(values)
                for row, value in zip(source, values):
                    chosen = selected and value == maximum
                    decisions.append({"record_id": row["record_id"], "source_column": column,
                                      "normalized_value": value, "selected_for_maximum": chosen,
                                      "selection_reason": reason if not selected else "supports_group_maximum" if chosen else "not_selected_lower_count"})
            candidates[-1]["field_decisions"] = decisions
        if kind.startswith("lit_") and selected:
            seen_links, seen_publications = set(), set()
            for r in sorted(relation_rows.values(), key=lambda r: r["source_record_number"]):
                link, publication = r["raw_fields"]["LitChem_id"], r["raw_fields"]["Lit_id"]
                counted_link = link is not None and link not in seen_links
                counted_publication = publication is not None and publication not in seen_publications
                link_decisions.append({"compound_key": key, "record_id": r["record_id"],
                    "chemical_record_ids": [s["record_id"] for s in source if s["raw_fields"]["Chem_id"] == r["raw_fields"]["Chem_id"]],
                    "Chem_id": r["raw_fields"]["Chem_id"], "LitChem_id": link, "Lit_id": publication,
                    "counted_link_record": counted_link, "counted_publication": counted_publication,
                    "link_reason": "missing_identifier" if link is None else "counted_unique_identifier" if counted_link else "duplicate_identifier_not_recounted",
                    "publication_reason": "missing_identifier" if publication is None else "counted_unique_identifier" if counted_publication else "duplicate_identifier_not_recounted"})
                seen_links.add(link); seen_publications.add(publication)

    if key in exact:
        add("lit_exact_key", key, exact[key], True, "exact_full_inchikey_precedence")
    for cas in cas_values:
        if cas in missing:
            selected = lit["match_method"] == "cas_fallback_source_inchikey_missing" and lit["matched_identifier"] == cas
            reason = "selected_unambiguous_cas_fallback" if selected else "excluded_exact_key_precedence" if lit["match_method"] == "exact_full_inchikey" else lit["match_method"]
            add("lit_missing_key_cas", cas, missing[cas], selected, reason)
        conflict = [r for r in all_cas[cas] if _normalize_inchikey(r["raw_fields"]["INCHIKEY"]) not in (None, key)]
        if conflict:
            add("lit_conflicting_key_cas", cas, conflict, False, "excluded_source_full_key_conflict")
        for table, label in (("fcchumon_s1", "FCChumon_S1"), ("fcchumon_s2", "FCChumon_S2")):
            if (table, cas) in fc:
                selected = human["selected"] and human["source_sheet"] == label and human["matched_cas"] == cas
                add(table, cas, fc[table, cas], selected, "selected_one_to_one_cas" if selected else human["match_method"])
    return candidates, link_decisions


@dataclass
class SpecialistEvidenceResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    cas_view: pd.DataFrame
    cas_links: pd.DataFrame
    anomalies: pd.DataFrame
    lit_audit: list
    human_audit: list
    candidates: list
    relationships: list
    source_rows: list
    conversions: list
    manifest: dict

    def write_reports(self, output_dir):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in (("compound_specialist_evidence", self.compounds), ("specialist_historical", self.historical),
                            ("cas_identity_view", self.cas_view), ("cas_source_links", self.cas_links),
                            ("identity_review_evidence", self.anomalies)):
            path = folder / (name + ".csv")
            frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            outputs[path.name] = _file_hash(path)
        for name, rows in (("litchemplast_resolution_audit", self.lit_audit),
                           ("fcchumon_resolution_audit", self.human_audit),
                           ("specialist_candidates", self.candidates), ("literature_link_decisions", self.relationships),
                           ("specialist_source_rows", self.source_rows), ("count_conversion_audit", self.conversions)):
            path = folder / (name + ".jsonl")
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(_json(row) + "\n")
            outputs[path.name] = _file_hash(path)
        (folder / "specialist_manifest.json").write_text(json.dumps({**self.manifest, "output_sha256": outputs}, indent=2) + "\n", encoding="utf-8")


def require_prediction_isolation(result):
    """Reject any upstream identity-review model value exposed to specialist analysis."""
    review = result["qsar_identity_status"].eq("review_required")
    qsar_fields = [c for c in json.loads(Path(__file__).with_name("qsar_models.json").read_text(encoding="utf-8"))["legacy_merge_columns"] if not c.startswith("Basic | ")]
    if result.loc[review, qsar_fields + VALUE_COLUMNS].ne("").any().any() or result.loc[review, ["qsar_evidence_available", "lrtp_available"]].ne("False").any().any():
        raise ValueError("An identity-review prediction bypassed upstream isolation.")


def integrate_specialist_evidence(stage2_results, basic_results, data_root="data"):
    """Attach independent source evidence while inheriting all model-identity exclusions."""
    stage2, basic = Path(stage2_results), Path(basic_results)
    if POLICY["schema_version"] != 1 or _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError("Specialist policy changed; restart the process.")
    paths = {"identity": stage2 / "identity_manifest.json", "basic": basic / "evidence_manifest.json"}
    fingerprints = {name: _file_hash(path) for name, path in paths.items()}
    manifests = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
    for name, folder in (("identity", stage2), ("basic", basic)):
        _verify_outputs(folder, manifests[name])
    if manifests["basic"]["upstream_manifests_sha256"]["identity"] != fingerprints["identity"]:
        raise ValueError("Stage 4A and Stage 2 refer to different identity runs.")
    if _file_hash(DEFAULT_CATALOG) != manifests["basic"]["catalog_sha256"]:
        raise ValueError("Source catalog differs from Stage 4A.")
    compounds = _read_csv(basic / "compound_evidence.csv")
    if compounds["inchikey"].duplicated().any():
        raise ValueError("Duplicate compound identities in Stage 4A.")
    records = _read_csv(stage2 / "resolved_records.csv")
    cas_view, cas_links = build_cas_view(compounds, _read_csv(stage2 / "compound_memberships.csv"),
                                       records, _read_csv(stage2 / "cas_mapping_audit.csv"))
    tables, sources, inputs = _load_specialist_tables(data_root, records,
        {s["source_filename"]: s["source_sha256"] for s in manifests["basic"]["inputs"]})
    conversions = _conversion_audit(sources)
    lit_index = build_litchemplast_indexes(tables["litchemplast"], tables["litchemplast_links"])
    human_index = build_fcchumon_indexes(tables["fcchumon_s1"], tables["fcchumon_s2"])
    trace_index = _trace_indexes(tables, sources)
    view = cas_view.set_index("inchikey")
    lit_audit, human_audit, candidates, relationships, history, analysis, anomalies = ([] for _ in range(7))
    for row in compounds.to_dict("records"):
        key = row["inchikey"]
        target = pd.Series({"Inchikey_std": key, **view.loc[key].to_dict()})
        lit = resolve_litchemplast_for_row(target, lit_index)
        human = resolve_fcchumon_for_row(target, human_index)
        lit_audit.append({"compound_key": key, **lit})
        human_audit.append({"compound_key": key, **human})
        candidate, relation = _candidate_trace(key, json.loads(target["cas_values_json"]), lit, human, trace_index)
        candidates.extend(candidate); relationships.extend(relation)
        payload = json.loads(row["db_extract_info"])
        literature = payload["exposure"]["literature"]
        if lit["selected"]:
            literature["litchemplast_count"] = {"LitChemPlast": [float(lit["linked_record_count"])]}
        else:
            literature.pop("litchemplast_count", None)
        payload.update(litchemplast_resolution=lit, fcchumon_resolution=human)
        member = "litchemplast" in json.loads(row["source_tables_json"])
        history.append({"inchikey": key, "db_extract_info": _json(payload),
                        "db_LitChemPlast": "1.0" if member or lit["selected"] else ""})
        state = ("detected" if human["detected"] else "matched_without_positive_count") if human["selected"] else human["match_method"]
        added = {"litchemplast_evidence_available": lit["selected"], "litchemplast_match_method": lit["match_method"],
                 "fcchumon_evidence_available": human["selected"], "fcchumon_evidence_status": state,
                 "fcchumon_detected": human["detected"] if human["selected"] else None}
        analysis.append({**row, "db_extract_info": _json(payload), **added})
        if row["qsar_identity_status"] == "review_required":
            anomalies.append({"inchikey": key, "qsar_inchikey": row["qsar_inchikey"], "vega_row_no": row["vega_row_no"],
                              "identity_reason": row["qsar_identity_reason"], "prediction_exclusion_reason": "identity_review_required",
                              "litchemplast_linked_record_count": lit["linked_record_count"],
                              "litchemplast_unique_publication_count": lit["unique_publication_count"], **added})
    result = pd.DataFrame(analysis)
    require_prediction_isolation(result)
    for name, path in paths.items():
        if _file_hash(path) != fingerprints[name]:
            raise ValueError("Upstream artifacts changed during Stage 4B.")
        _verify_outputs(path.parent, manifests[name])
    for item in inputs:
        if _file_hash(resolve_data_root(data_root) / "SourceDatabase" / item["filename"]) != item["sha256"]:
            raise ValueError("Specialist source changed during integration.")
    if _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError("Specialist policy changed during integration.")
    counts = {"compounds": len(result), "source_rows": len(sources), "cas_source_links": len(cas_links),
              "candidate_groups": len(candidates), "literature_link_decisions": len(relationships),
              "count_conversions": len(conversions), "identity_review_compounds": len(anomalies),
              "litchemplast_selected": sum(r["selected"] for r in lit_audit),
              "fcchumon_selected": sum(r["selected"] for r in human_audit),
              "fcchumon_detected": sum(r["detected"] for r in human_audit)}
    manifest = {"schema_version": 1, "scope": POLICY["scope"], "policy_sha256": POLICY_HASH,
                "implementation_sha256": _file_hash(Path(__file__)), "catalog_sha256": _file_hash(DEFAULT_CATALOG),
                "upstream_manifest_sha256": fingerprints, "inputs": inputs, "counts": counts,
                "litchemplast_index_summary": lit_index["summary"], "fcchumon_index_summary": human_index["summary"],
                "litchemplast_methods": dict(Counter(r["match_method"] for r in lit_audit)),
                "fcchumon_methods": dict(Counter(r["match_method"] for r in human_audit)),
                "runtime": {"python": platform.python_version(), "pandas": pd.__version__},
                "interpretation": POLICY["rules"], "historical_sources": POLICY["historical_sources"]}
    return SpecialistEvidenceResult(result, pd.DataFrame(history), cas_view, cas_links, pd.DataFrame(anomalies),
                                    lit_audit, human_audit, candidates, relationships, sources, conversions, manifest)
