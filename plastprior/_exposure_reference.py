"""Frozen historical exposure kernels for migration regression.

Symbols are namespaced ports of the source functions fingerprinted in
exposure_policy.json. Historical parsing, ordering and missingness are retained
here intentionally. The analysis path applies Stage 6A eligibility separately.
No legacy repository is imported or required at runtime.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional, Mapping, Iterable
from types import SimpleNamespace
import datetime as _dt
import hashlib
import json
import math
import re
import pandas as pd

tqdm = None
FCCHUMON_HUMAN_DETECTION_POLICY_VERSION = 'fcchumon-human-detection-one-to-one-cas-v1'
market_PRODUCTION_EVIDENCE_CLASSES = {'production_volume', 'registration_tonnage'}
market_MARKET_EVIDENCE_CLASSES = {'market_use', 'market_presence', 'national_statistics'}
market_SOURCE_BY_ID = {k: SimpleNamespace(selection_eligibility=v) for k, v in {'us_epa_cdr': 'eligible_compound_numeric', 'echa_reach': 'eligible_compound_numeric', 'nordic_spin': 'eligible_compound_numeric', 'japan_meti_cscl': 'eligible_compound_numeric', 'korea_chemical_statistics': 'national_context_only', 'canada_cepa_s71': 'eligible_compound_numeric', 'korea_new_chemicals': 'eligible_compound_numeric', 'taiwan_toxic_chemicals': 'eligible_compound_numeric'}.items()}


# Reference: Algorithm/exposure_scoring_policy.py
rules_EXPOSURE_SCORING_POLICY_VERSION = "exposure-five-dimension-discrete-v2"


rules_EXPOSURE_SCORE_LEVELS = (0.0, 0.5, 1.0, 2.0)


rules_EXPOSURE_DIMENSION_MAX_SCORE = 2.0


rules_EXPOSURE_TOTAL_MAX_SCORE = 10.0


rules_INVENTORY_SCORING_POLICY_VERSION = "gic-inventory-thresholds-v2"


rules_INVENTORY_SCORE_THRESHOLDS = (
    (1.0, 0.5),
    (2.0, 1.0),
    (4.0, 2.0),
)


rules_PRODUCTION_SCORING_POLICY_VERSION = "production-market-evidence-thresholds-v2"


rules_PRODUCTION_SCORE_THRESHOLDS_TONNES = (
    (1_000.0, 1.0),
    (100_000.0, 2.0),
)


rules_POSITIVE_MARKET_PRESENCE_STATUSES = frozenset(
    {
        "confirmed_positive_quantity",
        "confirmed_confidential_quantity",
        "confirmed_record_no_public_quantity",
        "historical_record",
    }
)


rules_AVAILABLE_MARKET_PRESENCE_STATUSES = rules_POSITIVE_MARKET_PRESENCE_STATUSES | {
    "confirmed_zero_quantity"
}


rules_PATENT_SCORING_POLICY_VERSION = "patent-count-thresholds-v2"


rules_PATENT_SCORE_THRESHOLDS = (
    (1.0, 0.5),
    (1_000.0, 1.0),
    (10_000.0, 2.0),
)


rules_LITERATURE_SCORING_POLICY_VERSION = "pubmed-count-thresholds-v1"


rules_LITERATURE_SCORE_THRESHOLDS = (
    (1.0, 0.5),
    (5.0, 1.0),
    (20.0, 2.0),
)


def rules__nonnegative_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0:
        return None
    return numeric


def rules__score_from_thresholds(
    value: Any,
    thresholds: tuple[tuple[float, float], ...],
) -> float:
    numeric = rules__nonnegative_float(value)
    if numeric is None:
        return 0.0
    score = 0.0
    for threshold, threshold_score in thresholds:
        if numeric >= threshold:
            score = threshold_score
    return score


def rules_inventory_score(listing_count: Any, data_status: Any = "available") -> float:
    """Score unique eligible-inventory count using the 1/2/4-list bands."""
    if str(data_status or "").strip().lower() != "available":
        return 0.0
    return rules__score_from_thresholds(listing_count, rules_INVENTORY_SCORE_THRESHOLDS)


def rules_production_market_score(value_tonnes: Any, market_presence: Any) -> float:
    """Score the selected numeric quantity or qualitative market presence."""
    numeric = rules__nonnegative_float(value_tonnes)
    if numeric is not None:
        if numeric >= 100_000:
            return 2.0
        if numeric >= 1_000:
            return 1.0
        if numeric > 0:
            return 0.5
    normalized_presence = str(market_presence or "").strip().lower()
    if normalized_presence in rules_POSITIVE_MARKET_PRESENCE_STATUSES:
        return 0.5
    return 0.0


def rules_production_market_data_available(value_tonnes: Any, market_presence: Any) -> bool:
    """Return whether a numeric or interpretable qualitative record is present."""
    if rules__nonnegative_float(value_tonnes) is not None:
        return True
    normalized_presence = str(market_presence or "").strip().lower()
    return normalized_presence in rules_AVAILABLE_MARKET_PRESENCE_STATUSES


def rules_patent_score(count: Any) -> float:
    """Score patent count using the 1/1,000/10,000 thresholds."""
    return rules__score_from_thresholds(count, rules_PATENT_SCORE_THRESHOLDS)


def rules_literature_score(count: Any) -> float:
    """Score PubMed Title/Abstract count using the 1/5/20 thresholds."""
    return rules__score_from_thresholds(count, rules_LITERATURE_SCORE_THRESHOLDS)


def rules_score_class(score: Any) -> str:
    """Return the publication display class for a canonical dimension score."""
    numeric = rules__nonnegative_float(score)
    if numeric == 0.0:
        return "Score 0"
    if numeric == 0.5:
        return "Low (0.5)"
    if numeric == 1.0:
        return "Moderate (1)"
    if numeric == 2.0:
        return "High (2)"
    raise ValueError(f"Exposure dimension score is outside the canonical levels: {score!r}")




# Reference: Algorithm/step20a_prepare_official_production_volume.py
cas_CASRN_PATTERN = re.compile(r"^[1-9]\d{1,6}-\d{2}-\d$")


def cas_is_valid_casrn(value: object) -> bool:
    """Return whether a value is a syntactically and checksum-valid CAS RN."""
    text = str(value or "").strip()
    if cas_CASRN_PATTERN.fullmatch(text) is None:
        return False
    digits = text.replace("-", "")
    checksum = sum(int(digit) * weight for weight, digit in enumerate(reversed(digits[:-1]), 1)) % 10
    return checksum == int(digits[-1])




# Reference: Algorithm/step20b_select_production_volume.py
official_PRODUCTION_POLICY_VERSION = "official-production-selection-v1"


official_OFFICIAL_SOURCE_SHORT = "US EPA CDR"


official_OFFICIAL_MATCH_METHOD = "representative_cas_unique_inchikey"


official_CASRN_FINDER = re.compile(r"(?<!\d)([1-9]\d{1,6}-\d{2}-\d)(?!\d)")


official_REQUIRED_OFFICIAL_COLUMNS = {
    "source",
    "jurisdiction",
    "source_release",
    "reporting_year",
    "source_row_number",
    "source_identifier",
    "casrn",
    "volume_raw",
    "volume_status",
    "volume_lower_tonnes",
    "volume_upper_tonnes",
    "source_unit",
    "normalised_unit",
    "source_archive",
    "source_member",
}


official_COMPACT_OFFICIAL_FIELDS = (
    "source",
    "jurisdiction",
    "source_release",
    "reporting_year",
    "source_row_number",
    "source_identifier",
    "casrn",
    "volume_raw",
    "volume_status",
    "volume_lower_tonnes",
    "volume_upper_tonnes",
    "source_unit",
    "normalised_unit",
    "source_archive",
    "source_archive_sha256",
    "source_member",
    "selected_tonnes",
    "selection_basis",
)


official_FALLBACK_JURISDICTIONS = {
    "usa_volume": "United States",
    "eu_volume": "European Union",
    "nordic_volume": "Nordic countries",
    "total_volume": "Multiple/unspecified",
}


official_FALLBACK_SOURCE_PRIORITY = {
    "PlastChem": 0,
}


official_ELIGIBLE_FALLBACK_SOURCES = frozenset(official_FALLBACK_SOURCE_PRIORITY)


def official__is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def official__as_float(value: Any) -> float | None:
    if official__is_missing(value):
        return None
    if isinstance(value, str):
        cleaned = (
            value.replace(",", "")
            .replace("tonnes", "")
            .replace("tons", "")
            .replace("t/y", "")
            .replace(">", "")
            .replace("<", "")
            .strip()
        )
        if "-" in cleaned and not cleaned.startswith("-"):
            parsed = [official__as_float(item) for item in cleaned.split("-")]
            usable = [item for item in parsed if item is not None]
            return max(usable) if usable else None
        value = cleaned
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def official__json_object(value: Any) -> dict[str, Any]:
    if official__is_missing(value):
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def official__normalise_inchikey(value: Any) -> str:
    return "" if official__is_missing(value) else str(value).strip().upper()


def official_extract_representative_casrns(value: Any) -> tuple[str, ...]:
    """Return checksum-valid CAS RNs from the final representative CAS field."""
    if official__is_missing(value):
        return ()
    candidates = official_CASRN_FINDER.findall(str(value))
    return tuple(dict.fromkeys(candidate for candidate in candidates if cas_is_valid_casrn(candidate)))


def official_build_representative_cas_index(
    compound_table: pd.DataFrame,
    *,
    cas_column: str = "CAS",
    inchikey_column: str = "Inchikey_std",
) -> dict[str, Any]:
    """Build a CAS index and separate safe one-to-one from ambiguous mappings."""
    missing = [column for column in (cas_column, inchikey_column) if column not in compound_table.columns]
    if missing:
        raise KeyError(f"Compound table is missing production matching columns: {missing}")

    cas_to_inchikeys: dict[str, set[str]] = defaultdict(set)
    compound_casrns: dict[str, tuple[str, ...]] = {}
    for row in compound_table[[inchikey_column, cas_column]].itertuples(index=False, name=None):
        inchikey = official__normalise_inchikey(row[0])
        if not inchikey:
            continue
        casrns = official_extract_representative_casrns(row[1])
        compound_casrns[inchikey] = casrns
        for casrn in casrns:
            cas_to_inchikeys[casrn].add(inchikey)

    unique = {
        casrn: next(iter(inchikeys))
        for casrn, inchikeys in cas_to_inchikeys.items()
        if len(inchikeys) == 1
    }
    ambiguous = {
        casrn: tuple(sorted(inchikeys))
        for casrn, inchikeys in cas_to_inchikeys.items()
        if len(inchikeys) > 1
    }
    return {
        "unique": unique,
        "ambiguous": ambiguous,
        "compound_casrns": compound_casrns,
        "cas_to_inchikeys": {key: tuple(sorted(value)) for key, value in cas_to_inchikeys.items()},
    }


def official__read_official_table(value: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        table = value.copy()
    else:
        path = Path(value).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Official production table does not exist: {path}")
        table = pd.read_csv(path, dtype="string", keep_default_na=False, encoding="utf-8")

    missing = sorted(official_REQUIRED_OFFICIAL_COLUMNS - set(table.columns))
    if missing:
        raise ValueError(f"Official production table is missing required columns: {missing}")
    return table


def official__selection_basis(volume_status: str) -> str | None:
    return {
        "exact": "reported_exact_value",
        "interval": "reported_interval_upper_bound",
        "upper_bound": "reported_upper_bound",
        "lower_bound": "reported_lower_bound",
    }.get(str(volume_status).strip())


def official__prepare_official_rows(table: pd.DataFrame) -> pd.DataFrame:
    prepared = table.copy()
    prepared["casrn"] = prepared["casrn"].astype("string").str.strip()
    prepared["reporting_year_number"] = pd.to_numeric(prepared["reporting_year"], errors="coerce")
    prepared["volume_lower_tonnes_number"] = pd.to_numeric(
        prepared["volume_lower_tonnes"], errors="coerce"
    )
    prepared["volume_upper_tonnes_number"] = pd.to_numeric(
        prepared["volume_upper_tonnes"], errors="coerce"
    )
    prepared["selected_tonnes"] = prepared["volume_upper_tonnes_number"].where(
        prepared["volume_upper_tonnes_number"].notna(),
        prepared["volume_lower_tonnes_number"],
    )
    prepared["selection_basis"] = prepared["volume_status"].map(official__selection_basis)
    prepared = prepared[
        prepared["casrn"].map(cas_is_valid_casrn)
        & prepared["reporting_year_number"].notna()
        & prepared["selected_tonnes"].notna()
        & prepared["selection_basis"].notna()
    ].copy()
    prepared["reporting_year_number"] = prepared["reporting_year_number"].astype(int)
    return prepared


def official__compact_official_record(row: Mapping[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for field in official_COMPACT_OFFICIAL_FIELDS:
        value = row.get(field)
        if official__is_missing(value):
            continue
        if field in {"reporting_year", "source_row_number"}:
            try:
                value = int(float(value))
            except (TypeError, ValueError):
                pass
        elif field in {"volume_lower_tonnes", "volume_upper_tonnes", "selected_tonnes"}:
            numeric = official__as_float(value)
            value = numeric if numeric is not None else value
        record[field] = value
    return record


def official_build_official_production_selections(
    compound_table: pd.DataFrame,
    official_table: str | Path | pd.DataFrame,
    *,
    cas_column: str = "CAS",
    inchikey_column: str = "Inchikey_std",
    source_archive_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build compact, deterministic EPA selections keyed by standardized InChIKey."""
    cas_index = official_build_representative_cas_index(
        compound_table,
        cas_column=cas_column,
        inchikey_column=inchikey_column,
    )
    official_raw = official__read_official_table(official_table)
    if source_archive_sha256:
        official_raw["source_archive_sha256"] = official_raw["source_archive"].map(
            source_archive_sha256
        )
    official = official__prepare_official_rows(official_raw)
    official_casrns = set(official["casrn"].astype(str))
    unique_map: dict[str, str] = cas_index["unique"]
    ambiguous_map: dict[str, tuple[str, ...]] = cas_index["ambiguous"]

    matched = official[official["casrn"].isin(unique_map)].copy()
    matched["inchikey_std"] = matched["casrn"].map(unique_map)
    records_by_inchikey: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in matched.to_dict(orient="records"):
        records_by_inchikey[str(record["inchikey_std"])].append(record)

    selections: dict[str, dict[str, Any]] = {}
    match_status_counts: Counter[str] = Counter()
    reporting_year_counts: Counter[str] = Counter()
    value_status_counts: Counter[str] = Counter()

    for row in compound_table[[inchikey_column, cas_column]].itertuples(index=False, name=None):
        inchikey = official__normalise_inchikey(row[0])
        if not inchikey:
            continue
        casrns = official_extract_representative_casrns(row[1])
        unique_casrns = tuple(casrn for casrn in casrns if unique_map.get(casrn) == inchikey)
        ambiguous_casrns = tuple(casrn for casrn in casrns if casrn in ambiguous_map)
        ambiguous_official_casrns = tuple(
            casrn for casrn in ambiguous_casrns if casrn in official_casrns
        )
        candidates = records_by_inchikey.get(inchikey, [])

        if candidates:
            latest_year = max(int(record["reporting_year_number"]) for record in candidates)
            latest = [
                record for record in candidates
                if int(record["reporting_year_number"]) == latest_year
            ]
            latest.sort(
                key=lambda record: (
                    -float(record["selected_tonnes"]),
                    str(record.get("casrn", "")),
                    str(record.get("source_release", "")),
                    str(record.get("source_row_number", "")),
                )
            )
            selected = official__compact_official_record(latest[0])
            selected["source_label"] = official_OFFICIAL_SOURCE_SHORT
            considered = [official__compact_official_record(record) for record in latest]
            status = "unique_match"
            reporting_year_counts[str(latest_year)] += 1
            value_status_counts[str(selected.get("volume_status", "unknown"))] += 1
        elif ambiguous_official_casrns:
            selected = None
            considered = []
            status = "ambiguous_official_cas_match"
        elif casrns:
            selected = None
            considered = []
            status = "no_official_record"
        else:
            selected = None
            considered = []
            status = "no_representative_cas"

        match_status_counts[status] += 1
        selections[inchikey] = {
            "policy_version": official_PRODUCTION_POLICY_VERSION,
            "match_status": status,
            "match_method": official_OFFICIAL_MATCH_METHOD,
            "official_selected_record": selected,
            "considered_candidates": considered,
            "matched_casrns": list(unique_casrns if selected is not None else ()),
            "ambiguous_casrns": list(ambiguous_casrns),
            "ambiguous_official_casrns": list(ambiguous_official_casrns),
        }

    summary = {
        "policy_version": official_PRODUCTION_POLICY_VERSION,
        "official_rows_total": int(len(official_raw)),
        "official_rows_usable": int(len(official)),
        "official_unique_casrns_usable": int(official["casrn"].nunique()),
        "representative_casrns": int(len(cas_index["cas_to_inchikeys"])),
        "unique_representative_casrns": int(len(unique_map)),
        "ambiguous_representative_casrns": int(len(ambiguous_map)),
        "official_casrns_with_unique_compound_match": int(len(official_casrns & set(unique_map))),
        "official_casrns_with_ambiguous_compound_match": int(len(official_casrns & set(ambiguous_map))),
        "official_selected_compounds": int(match_status_counts.get("unique_match", 0)),
        "match_status_counts": dict(sorted(match_status_counts.items())),
        "selected_reporting_year_counts": dict(sorted(reporting_year_counts.items())),
        "selected_value_status_counts": dict(sorted(value_status_counts.items())),
    }
    return {
        "selections": selections,
        "summary": summary,
        "cas_index": cas_index,
    }


def official__iter_fallback_values(production: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(production, dict):
        return
    for scope, sources in production.items():
        if not isinstance(sources, dict):
            continue
        for source, values in sources.items():
            if str(source) not in official_ELIGIBLE_FALLBACK_SOURCES:
                continue
            items = values if isinstance(values, list) else [values]
            for value in items:
                numeric = official__as_float(value)
                if numeric is None:
                    continue
                yield {
                    "source": str(source),
                    "scope": str(scope),
                    "jurisdiction": official_FALLBACK_JURISDICTIONS.get(str(scope), "Unspecified"),
                    "selected_tonnes": numeric,
                    "volume_status": "reported_value",
                    "selection_basis": "existing_database_fallback_max",
                }


def official_select_existing_production_fallback(production: Any) -> dict[str, Any] | None:
    """Return the maximum existing production value with its source and scope."""
    candidates = list(official__iter_fallback_values(production))
    if not candidates:
        return None
    candidates.sort(
        key=lambda record: (
            -float(record["selected_tonnes"]),
            official_FALLBACK_SOURCE_PRIORITY.get(str(record["source"]), 99),
            0 if record["scope"] == "total_volume" else 1,
            str(record["source"]),
            str(record["scope"]),
        )
    )
    return candidates[0]


def official_resolve_production_selection(
    existing_production: Any,
    official_decision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Combine an official decision with the existing-database fallback."""
    decision = dict(official_decision or {})
    fallback = official_select_existing_production_fallback(existing_production)
    official = decision.get("official_selected_record")

    if isinstance(official, dict) and official:
        selected = dict(official)
        selected["source"] = selected.get("source_label") or official_OFFICIAL_SOURCE_SHORT
        selected.pop("source_label", None)
        fallback_record = fallback
    elif fallback is not None:
        selected = dict(fallback)
        fallback_record = None
    else:
        selected = None
        fallback_record = None

    audit = {
        "policy_version": decision.get("policy_version", official_PRODUCTION_POLICY_VERSION),
        "match_status": decision.get("match_status", "official_data_not_configured"),
        "match_method": decision.get("match_method", official_OFFICIAL_MATCH_METHOD),
        "selected_record": selected,
        "fallback_record": fallback_record,
        "considered_candidates": list(decision.get("considered_candidates") or []),
        "matched_casrns": list(decision.get("matched_casrns") or []),
        "ambiguous_casrns": list(decision.get("ambiguous_casrns") or []),
        "ambiguous_official_casrns": list(
            decision.get("ambiguous_official_casrns") or []
        ),
    }
    return {
        "selected_record": selected,
        "audit": audit,
    }




# Reference: Algorithm/step20c_external_exposure_evidence.py
external_PATENT_POLICY_VERSION = "pubchem-patent-zero-correction-v1"


external_LITERATURE_POLICY_VERSION = "pubmed-title-abstract-scoring-v1"


external_PATENT_TERMINAL_STATUSES = {
    "pubchem_patent_ids_found",
    "pubchem_no_patent_ids",
}


external_PATENT_REQUIRED_COLUMNS = {
    "Inchikey_std",
    "existing_patent_count",
    "pubchem_cids",
    "pubchem_patent_count",
    "check_status",
    "count_method",
    "source_url",
    "checked_at",
    "error_message",
}


external_LITERATURE_REQUIRED_COLUMNS = {
    "Inchikey_std",
    "candidate_terms_json",
    "pubmed_query",
    "pubmed_query_url",
    "pubmed_title_abstract_count",
    "status",
    "retrieved_at_utc",
    "error_message",
}


def external__sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def external__is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def external__json_value(value: Any) -> Any:
    if external__is_missing(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def external__as_float(value: Any) -> float | None:
    if external__is_missing(value) or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def external__normalise_inchikey(value: Any) -> str:
    if external__is_missing(value):
        return ""
    return str(value).strip().upper()


def external__normalise_compound_keys(values: Iterable[Any]) -> set[str]:
    return {key for key in (external__normalise_inchikey(value) for value in values) if key}


def external__load_records(
    path: str | Path,
    *,
    required_columns: set[str],
    status_column: str,
    compound_inchikeys: Iterable[Any],
    policy_version: str,
    scoring_mode: str,
) -> dict[str, Any]:
    source_path = Path(path).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"External exposure evidence file was not found: {source_path}")

    table = pd.read_csv(source_path, encoding="utf-8-sig", low_memory=False)
    missing_columns = sorted(required_columns - set(table.columns))
    if missing_columns:
        raise KeyError(
            f"{source_path.name} is missing required columns: {missing_columns}"
        )

    table = table.copy()
    table["_inchikey"] = table["Inchikey_std"].map(external__normalise_inchikey)
    if table["_inchikey"].eq("").any():
        rows = table.index[table["_inchikey"].eq("")].tolist()[:5]
        raise ValueError(f"{source_path.name} contains blank InChIKeys at rows: {rows}")
    duplicates = table.loc[table["_inchikey"].duplicated(), "_inchikey"].unique().tolist()
    if duplicates:
        raise ValueError(
            f"{source_path.name} contains duplicate full InChIKeys: {duplicates[:5]}"
        )

    compound_keys = external__normalise_compound_keys(compound_inchikeys)
    source_keys = set(table["_inchikey"])
    matched_table = table.loc[table["_inchikey"].isin(compound_keys)].copy()
    records = {
        str(row["_inchikey"]): {
            str(column): external__json_value(row[column])
            for column in matched_table.columns
            if column != "_inchikey"
        }
        for _, row in matched_table.iterrows()
    }
    status_counts = Counter(
        str(value).strip() if not external__is_missing(value) and str(value).strip() else "missing"
        for value in table[status_column]
    )
    error_rows = int(
        table["error_message"].fillna("").astype(str).str.strip().ne("").sum()
    )
    summary = {
        "enabled": True,
        "policy_version": policy_version,
        "scoring_mode": scoring_mode,
        "source_filename": source_path.name,
        "source_sha256": external__sha256(source_path),
        "rows": int(len(table)),
        "unique_full_inchikeys": int(len(source_keys)),
        "matched_input_rows": int(len(source_keys & compound_keys)),
        "unmatched_input_rows": int(len(source_keys - compound_keys)),
        "unmatched_compounds": int(len(compound_keys - source_keys)),
        "returned_records": int(len(records)),
        "status_counts": dict(sorted(status_counts.items())),
        "error_rows": error_rows,
    }
    return {"records": records, "summary": summary}


def external_load_patent_zero_corrections(
    path: str | Path,
    compound_inchikeys: Iterable[Any],
) -> dict[str, Any]:
    """Load the PubChem zero-count follow-up file."""
    return external__load_records(
        path,
        required_columns=external_PATENT_REQUIRED_COLUMNS,
        status_column="check_status",
        compound_inchikeys=compound_inchikeys,
        policy_version=external_PATENT_POLICY_VERSION,
        scoring_mode="zero_count_correction",
    )


def external_load_pubmed_query_audit(
    path: str | Path,
    compound_inchikeys: Iterable[Any],
) -> dict[str, Any]:
    """Load PubMed title/abstract query counts as formal scoring evidence."""
    return external__load_records(
        path,
        required_columns=external_LITERATURE_REQUIRED_COLUMNS,
        status_column="status",
        compound_inchikeys=compound_inchikeys,
        policy_version=external_LITERATURE_POLICY_VERSION,
        scoring_mode="formal_scoring",
    )


def external_resolve_patent_selection(
    database_extract_count: float,
    pubchemlite_count: float,
    external_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Select a patent count without adding overlapping source counts."""
    extract_count = max(0.0, float(database_extract_count or 0.0))
    lite_count = max(0.0, float(pubchemlite_count or 0.0))
    if lite_count > extract_count:
        fallback_source = "PubChemLite"
        fallback_count = lite_count
    elif extract_count > 0:
        fallback_source = "curated_database_extract"
        fallback_count = extract_count
    else:
        fallback_source = None
        fallback_count = 0.0

    record = dict(external_record or {})
    external_count = external__as_float(record.get("pubchem_patent_count"))
    status = str(record.get("check_status") or "").strip()
    error_message = str(record.get("error_message") or "").strip()
    existing_count = external__as_float(record.get("existing_patent_count"))
    external_eligible = (
        bool(record)
        and fallback_count == 0.0
        and (existing_count is None or existing_count == 0.0)
        and status in external_PATENT_TERMINAL_STATUSES
        and external_count is not None
        and not error_message
    )

    if external_eligible:
        selected_count = max(0.0, float(external_count))
        selected_source = "PubChem PUG-REST PatentID"
        selection_basis = "validated_zero_count_correction"
        quality_status = "complete"
    else:
        selected_count = fallback_count
        selected_source = fallback_source
        selection_basis = "existing_evidence_fallback"
        if not record:
            quality_status = "not_audited_nonzero_or_out_of_scope"
        elif error_message:
            quality_status = "review_required_error_message"
        elif status == "no_pubchem_cid":
            quality_status = "no_pubchem_cid"
        elif external_count is None:
            quality_status = "missing_external_count"
        elif fallback_count > 0:
            quality_status = "existing_nonzero_retained"
        else:
            quality_status = "not_eligible"

    audit = {
        "policy_version": external_PATENT_POLICY_VERSION,
        "selected_count": selected_count,
        "selected_source": selected_source,
        "selection_basis": selection_basis,
        "quality_status": quality_status,
        "scoring_eligible": bool(external_eligible or fallback_count > 0),
        "fallback_record": {
            "source": fallback_source,
            "count": fallback_count,
            "database_extract_count": extract_count,
            "pubchemlite_count": lite_count,
        },
        "external_record": record or None,
    }
    return {"selected_count": selected_count, "audit": audit}


def external_build_literature_query_audit(
    litchemplast_count: float,
    external_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Select validated PubMed query hits as the formal Literature count."""
    record = dict(external_record or {})
    status = str(record.get("status") or "").strip()
    error_message = str(record.get("error_message") or "").strip()
    query_count = external__as_float(record.get("pubmed_title_abstract_count"))
    query_available = status == "ok" and query_count is not None and not error_message
    selected_count = max(0.0, float(query_count)) if query_available else 0.0
    audit = {
        "policy_version": external_LITERATURE_POLICY_VERSION,
        "scoring_mode": "formal_scoring",
        "selected_scoring_count": selected_count,
        "selected_scoring_source": "NCBI PubMed Title/Abstract",
        "selection_basis": "validated_pubmed_title_abstract_query_count",
        "data_status": "available" if query_available else "unavailable",
        "legacy_litchemplast_count": max(0.0, float(litchemplast_count or 0.0)),
        "pubmed_query_count": selected_count if query_available else None,
        "query_quality_status": (
            "unreviewed_query_hits"
            if query_available
            else "no_candidate_term"
            if status == "no_candidate_term"
            else "review_required"
        ),
        "scoring_eligible": query_available,
        "external_record": record or None,
    }
    return {
        "pubmed_query_count": audit["pubmed_query_count"],
        "selected_count": selected_count,
        "selected_source": audit["selected_scoring_source"],
        "data_status": audit["data_status"],
        "policy_version": external_LITERATURE_POLICY_VERSION,
        "audit": audit,
    }




# Reference: production_evidence/selection.py
market_SELECTION_POLICY_VERSION = "production-market-historical-max-v2"


market_PLASTCHEM_SOURCE_URL = "https://plastchem-project.org/"


market_PLASTCHEM_DATASET_URL = "https://zenodo.org/records/15397723"


market_SELECTION_FIELDS = [
    "Inchikey_std",
    "CAS",
    "Name_std",
    "Exposure_scale_value_tonnes",
    "Exposure_scale_lower_tonnes",
    "Exposure_scale_upper_tonnes",
    "Exposure_scale_source",
    "Exposure_scale_source_id",
    "Exposure_scale_metric_type",
    "Exposure_scale_activity",
    "Exposure_scale_jurisdiction",
    "Exposure_scale_reporting_period",
    "Exposure_scale_value_status",
    "Exposure_scale_market_presence",
    "Exposure_scale_has_numeric",
    "Exposure_scale_has_production_numeric",
    "Exposure_scale_has_market_use_numeric",
    "Exposure_scale_evidence_count",
    "Exposure_scale_numeric_evidence_count",
    "Exposure_scale_eligible_numeric_count",
    "Exposure_scale_source_count",
    "Exposure_scale_numeric_source_count",
    "Exposure_scale_source_url",
    "Exposure_scale_dataset_url",
    "Exposure_scale_record_id",
    "Exposure_scale_audit_relative_path",
    "Exposure_scale_selection_policy",
    "Exposure_scale_selection_reason",
]


market__PRESENCE_PRIORITY = {
    "": 0,
    "unknown": 0,
    "not_found_in_source": 1,
    "confirmed_zero_quantity": 2,
    "historical_record": 3,
    "confirmed_record_no_public_quantity": 4,
    "confirmed_confidential_quantity": 5,
    "confirmed_positive_quantity": 6,
}


market__VALUE_STATUS_PRIORITY = {
    "reported_zero": 1,
    "upper_bound": 2,
    "lower_bound": 3,
    "range": 4,
    "interval": 4,
    "reported_value": 5,
    "exact": 5,
}


market__METRIC_PRIORITY = {
    "compiled_production_volume": 1,
    "market_presence": 1,
    "market_use": 2,
    "registration_tonnage": 3,
    "production_volume": 4,
}


market__ELIGIBLE_IDENTITY_STATUSES = {
    "unique_dashboard_match",
    "native_inchikey_match",
    "legacy_inchikey_compound_record",
}


def market__text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def market__decimal(value: Any) -> Decimal | None:
    raw = market__text(value).replace(",", "")
    if not raw:
        return None
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def market__decimal_output(value: Decimal | None) -> str:
    if value is None:
        return ""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def market__year(value: Any) -> int | None:
    raw = market__text(value)
    if not raw:
        return None
    try:
        number = int(float(raw))
    except (TypeError, ValueError):
        return None
    return number if 1800 <= number <= 3000 else None


def market__selected_quantity(lower: Decimal | None, upper: Decimal | None) -> tuple[Decimal | None, str]:
    if upper is not None:
        return upper, "reported_upper_bound_or_exact_value"
    if lower is not None:
        return lower, "reported_lower_bound"
    return None, "no_numeric_quantity"


def market__source_candidate_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    """Rank within one source by value; use year only as a tie-break."""
    year = candidate.get("reporting_year_number")
    return (
        Decimal(candidate["selected_tonnes_decimal"]),
        market__VALUE_STATUS_PRIORITY.get(market__text(candidate.get("value_status")).lower(), 0),
        1 if year is not None else 0,
        int(year) if year is not None else -1,
        market__text(candidate.get("record_id")),
    )


def market__final_candidate_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    """Rank across sources without adding incomparable quantities."""
    return (
        Decimal(candidate["selected_tonnes_decimal"]),
        market__VALUE_STATUS_PRIORITY.get(market__text(candidate.get("value_status")).lower(), 0),
        market__METRIC_PRIORITY.get(market__text(candidate.get("metric_type")).lower(), 0),
        market__text(candidate.get("source_id")),
        market__text(candidate.get("record_id")),
    )


def market__canonical_candidate(row: Mapping[str, str]) -> dict[str, Any]:
    lower = market__decimal(row.get("quantity_lower_tonnes"))
    upper = market__decimal(row.get("quantity_upper_tonnes"))
    selected, basis = market__selected_quantity(lower, upper)
    return {
        "record_id": market__text(row.get("record_id")),
        "source_id": market__text(row.get("source_id")),
        "source_name": market__text(row.get("source_name")),
        "metric_type": market__text(row.get("evidence_class")),
        "evidence_class": market__text(row.get("evidence_class")),
        "activity": market__text(row.get("activity")),
        "jurisdiction": market__text(row.get("jurisdiction")),
        "reporting_period": market__text(row.get("reporting_period")),
        "reporting_year": market__text(row.get("reporting_year")),
        "reporting_year_number": market__year(row.get("reporting_year")),
        "value_status": market__text(row.get("value_status")),
        "quantity_lower_tonnes": market__decimal_output(lower),
        "quantity_upper_tonnes": market__decimal_output(upper),
        "selected_tonnes": market__decimal_output(selected),
        "selected_tonnes_decimal": selected,
        "selection_basis": basis,
        "market_presence": market__text(row.get("market_presence")),
        "source_url": market__text(row.get("source_url")),
        "dataset_url": market__text(row.get("dataset_url")),
        "audit_relative_path": market__text(row.get("audit_relative_path")),
        "identity_match_status": market__text(row.get("identity_match_status")),
        "non_additive_warning": market__text(row.get("non_additive_warning")),
        "is_legacy": False,
    }


def market_iter_legacy_plastchem_candidates(row: pd.Series, inchikey: str) -> Iterable[dict[str, Any]]:
    """Yield only PlastChem legacy values; UCSF is intentionally ineligible."""
    raw = row.get("db_extract_info")
    if not market__text(raw):
        return
    try:
        parsed = raw if isinstance(raw, dict) else json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return
    exposure = parsed.get("exposure") if isinstance(parsed, dict) else None
    production = exposure.get("production") if isinstance(exposure, dict) else None
    if not isinstance(production, dict):
        return
    for scope, sources in production.items():
        if not isinstance(sources, dict):
            continue
        values = sources.get("PlastChem")
        if values is None:
            continue
        for index, value in enumerate(values if isinstance(values, list) else [values]):
            number = market__decimal(value)
            if number is None or number < 0:
                continue
            rendered = market__decimal_output(number)
            yield {
                "record_id": f"plastchem:{inchikey}:{scope}:{index}",
                "source_id": "plastchem",
                "source_name": "PlastChem",
                "metric_type": "compiled_production_volume",
                "evidence_class": "compiled_production_volume",
                "activity": market__text(scope),
                "jurisdiction": {
                    "usa_volume": "United States",
                    "eu_volume": "European Union",
                    "nordic_volume": "Nordic countries",
                    "total_volume": "Multiple/unspecified",
                }.get(market__text(scope), "Unspecified"),
                "reporting_period": "",
                "reporting_year": "",
                "reporting_year_number": None,
                "value_status": "reported_value",
                "quantity_lower_tonnes": rendered,
                "quantity_upper_tonnes": rendered,
                "selected_tonnes": rendered,
                "selected_tonnes_decimal": number,
                "selection_basis": "legacy_database_reported_value",
                "market_presence": (
                    "confirmed_positive_quantity" if number > 0 else "confirmed_zero_quantity"
                ),
                "source_url": market_PLASTCHEM_SOURCE_URL,
                "dataset_url": market_PLASTCHEM_DATASET_URL,
                "audit_relative_path": "",
                "identity_match_status": "legacy_inchikey_compound_record",
                "non_additive_warning": "compiled_source_may_overlap_official_sources",
                "is_legacy": True,
            }


@dataclass
class market_CompoundSelectionState:
    inchikey: str
    cas: str
    name: str
    evidence_count: int = 0
    numeric_evidence_count: int = 0
    eligible_numeric_count: int = 0
    production_numeric_count: int = 0
    market_numeric_count: int = 0
    sources: set[str] = field(default_factory=set)
    numeric_sources: set[str] = field(default_factory=set)
    best_presence: str = "unknown"
    best_by_source: dict[str, dict[str, Any]] = field(default_factory=dict)
    rejected: Counter[str] = field(default_factory=Counter)

    def add(self, candidate: dict[str, Any], *, canonical: bool = True) -> None:
        self.evidence_count += 1
        source_id = market__text(candidate.get("source_id"))
        presence = market__text(candidate.get("market_presence"))
        if market__PRESENCE_PRIORITY.get(presence, 0) > market__PRESENCE_PRIORITY.get(self.best_presence, 0):
            self.best_presence = presence

        selected = candidate.get("selected_tonnes_decimal")
        if source_id and (
            selected is not None
            or presence not in {"", "unknown", "not_found_in_source"}
        ):
            self.sources.add(source_id)
        if selected is None:
            self.rejected["no_numeric_quantity"] += 1
            return
        self.numeric_evidence_count += 1

        identity_status = market__text(candidate.get("identity_match_status"))
        if identity_status not in market__ELIGIBLE_IDENTITY_STATUSES:
            self.rejected[f"identity:{identity_status or 'missing'}"] += 1
            return
        source_definition = market_SOURCE_BY_ID.get(source_id)
        if (
            source_definition is not None
            and source_definition.selection_eligibility != "eligible_compound_numeric"
        ):
            self.rejected[source_definition.selection_eligibility] += 1
            return

        self.eligible_numeric_count += 1
        self.numeric_sources.add(source_id)
        evidence_class = market__text(candidate.get("evidence_class"))
        if evidence_class in market_PRODUCTION_EVIDENCE_CLASSES or evidence_class == "compiled_production_volume":
            self.production_numeric_count += 1
        if evidence_class in market_MARKET_EVIDENCE_CLASSES:
            self.market_numeric_count += 1

        existing = self.best_by_source.get(source_id)
        if existing is None or market__source_candidate_key(candidate) > market__source_candidate_key(existing):
            self.best_by_source[source_id] = candidate

    def selected(self) -> dict[str, Any] | None:
        if not self.best_by_source:
            return None
        return max(self.best_by_source.values(), key=market__final_candidate_key)


def market__public_candidate(candidate: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        key: value
        for key, value in candidate.items()
        if key not in {"selected_tonnes_decimal", "reporting_year_number"}
    }


def market__selection_row(state: market_CompoundSelectionState) -> dict[str, Any]:
    selected = state.selected()
    row = {field: "" for field in market_SELECTION_FIELDS}
    row.update(
        {
            "Inchikey_std": state.inchikey,
            "CAS": state.cas,
            "Name_std": state.name,
            "Exposure_scale_market_presence": state.best_presence,
            "Exposure_scale_has_numeric": int(selected is not None),
            "Exposure_scale_has_production_numeric": int(state.production_numeric_count > 0),
            "Exposure_scale_has_market_use_numeric": int(state.market_numeric_count > 0),
            "Exposure_scale_evidence_count": state.evidence_count,
            "Exposure_scale_numeric_evidence_count": state.numeric_evidence_count,
            "Exposure_scale_eligible_numeric_count": state.eligible_numeric_count,
            "Exposure_scale_source_count": len(state.sources),
            "Exposure_scale_numeric_source_count": len(state.numeric_sources),
            "Exposure_scale_selection_policy": market_SELECTION_POLICY_VERSION,
            "Exposure_scale_selection_reason": (
                "maximum_historical_conservative_proxy_across_all_sources"
                if selected is not None
                else "no_eligible_numeric_evidence"
            ),
        }
    )
    if selected is None:
        return row
    row.update(
        {
            "Exposure_scale_value_tonnes": selected["selected_tonnes"],
            "Exposure_scale_lower_tonnes": selected["quantity_lower_tonnes"],
            "Exposure_scale_upper_tonnes": selected["quantity_upper_tonnes"],
            "Exposure_scale_source": selected["source_name"],
            "Exposure_scale_source_id": selected["source_id"],
            "Exposure_scale_metric_type": selected["metric_type"],
            "Exposure_scale_activity": selected["activity"],
            "Exposure_scale_jurisdiction": selected["jurisdiction"],
            "Exposure_scale_reporting_period": selected["reporting_period"],
            "Exposure_scale_value_status": selected["value_status"],
            "Exposure_scale_source_url": selected["source_url"],
            "Exposure_scale_dataset_url": selected["dataset_url"],
            "Exposure_scale_record_id": selected["record_id"],
            "Exposure_scale_audit_relative_path": selected["audit_relative_path"],
        }
    )
    return row




# Reference: Algorithm/step20_exposure_scoring.py
legacy_EXPOSURE_SCALE_OUTPUT_COLUMNS = [
    "Exposure_scale_value_tonnes",
    "Exposure_scale_lower_tonnes",
    "Exposure_scale_upper_tonnes",
    "Exposure_scale_source",
    "Exposure_scale_source_id",
    "Exposure_scale_metric_type",
    "Exposure_scale_activity",
    "Exposure_scale_jurisdiction",
    "Exposure_scale_reporting_period",
    "Exposure_scale_value_status",
    "Exposure_scale_market_presence",
    "Exposure_scale_has_numeric",
    "Exposure_scale_has_production_numeric",
    "Exposure_scale_has_market_use_numeric",
    "Exposure_scale_evidence_count",
    "Exposure_scale_numeric_evidence_count",
    "Exposure_scale_eligible_numeric_count",
    "Exposure_scale_source_count",
    "Exposure_scale_numeric_source_count",
    "Exposure_scale_source_url",
    "Exposure_scale_dataset_url",
    "Exposure_scale_record_id",
    "Exposure_scale_audit_relative_path",
    "Exposure_scale_selection_policy",
    "Exposure_scale_selection_reason",
]


legacy_EXPOSURE_OUTPUT_COLUMNS = [
    *legacy_EXPOSURE_SCALE_OUTPUT_COLUMNS,
    "Exposure_prod_total_tons",
    "Exposure_prod_source",
    "Exposure_prod_jurisdiction",
    "Exposure_prod_reporting_year",
    "Exposure_prod_value_status",
    "Exposure_production_data_status",
    "Exposure_patent_count",
    "Exposure_patent_data_status",
    "Exposure_patent_source",
    "Exposure_patent_policy",
    "Exposure_litchemplast_count",
    "Exposure_pubmed_title_abstract_count",
    "Exposure_literature_count",
    "Exposure_literature_data_status",
    "Exposure_literature_source",
    "Exposure_literature_policy",
    "Exposure_FCCmigex_listed",
    "Exposure_food_contact_data_status",
    "Exposure_FCChumon_S1_listed",
    "Exposure_FCChumon_S2_listed",
    "Exposure_FCChumon_S1_detected",
    "Exposure_FCChumon_S2_detected",
    "Exposure_FCChumon_detection_count",
    "Exposure_FCChumon_detection_data_status",
    "Exposure_FCChumon_detection_match_method",
    "Exposure_FCChumon_detection_policy",
    "Exposure_inventory_listing_count",
    "Exposure_inventory_list_tags",
    "Exposure_inventory_data_status",
    "Exposure_food_contact_score",
    "Exposure_human_biomonitoring_score",
    "Exposure_inventory_score",
    "Exposure_production_score",
    "Exposure_patent_score",
    "Exposure_literature_score",
    "Exposure_score",
    "Exposure_score_basis",
    "Exposure_evidence",
]


legacy_EXPOSURE_DIMENSION_INDICATORS = {
    "production_or_market_scale": ("production",),
    "patent_activity": ("patent",),
    "literature_frequency": ("literature",),
    "food_contact_and_biomonitoring_evidence": (
        "food_contact",
        "human_biomonitoring",
    ),
    "curated_inventory_presence": ("inventory_presence_proxy",),
}


def legacy__is_nullish(v: Any) -> bool:
    if v is None:
        return True
    try:
        if bool(pd.isna(v)):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def legacy__safe_json_loads(x: Any) -> Optional[dict]:
    if legacy__is_nullish(x):
        return None
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x)
    except Exception:
        return None


def legacy__json_default(o: Any) -> Any:
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    if o.__class__.__name__ == "Timestamp":
        try:
            return o.isoformat()
        except Exception:
            return str(o)
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def legacy__json_dumps_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=legacy__json_default)


def legacy__as_float(v: Any) -> Optional[float]:
    if legacy__is_nullish(v):
        return None
    if isinstance(v, str):
        cleaned = (
            v.replace(",", "")
            .replace(">", "")
            .replace("<", "")
            .replace("tons", "")
            .replace("tonnes", "")
            .replace("t/y", "")
            .strip()
        )
        if "-" in cleaned:
            parts = [legacy__as_float(part) for part in cleaned.split("-")]
            parts = [part for part in parts if part is not None]
            return max(parts) if parts else None
        v = cleaned
    try:
        return float(v)
    except Exception:
        return None


def legacy__truthy_indicator(v: Any) -> int:
    if legacy__is_nullish(v):
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(float(v) != 0)
    if isinstance(v, str):
        return int(v.strip().lower() in {"1", "true", "t", "yes", "y", "present", "listed"})
    return int(bool(v))


def legacy__iter_nested_values(obj: Any):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from legacy__iter_nested_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from legacy__iter_nested_values(value)
    else:
        yield obj


def legacy__max_numeric_from_nested(obj: Any) -> float:
    values = [legacy__as_float(value) for value in legacy__iter_nested_values(obj)]
    values = [value for value in values if value is not None]
    return max(values) if values else 0.0


def legacy__load_pubchemlite_patent_lookup(pubchemlite_path: str | Path | None) -> dict[str, float]:
    """Load PubChemLite patent counts keyed by full InChIKey."""
    if pubchemlite_path is None:
        return {}

    path = Path(pubchemlite_path).expanduser()
    if not path.exists():
        return {}

    raw = pd.read_csv(path, usecols=["InChIKey", "Patent_Count"], encoding="utf-8")
    raw = raw.dropna(subset=["InChIKey"]).copy()
    raw["InChIKey"] = raw["InChIKey"].astype("string").str.strip().str.upper()
    raw["Patent_Count"] = raw["Patent_Count"].map(legacy__as_float)
    raw = raw.dropna(subset=["Patent_Count"])
    if raw.empty:
        return {}

    grouped = raw.groupby("InChIKey", dropna=True)["Patent_Count"].max()
    return {str(key): float(value) for key, value in grouped.items()}


def legacy__lookup_patent_count(row: pd.Series, patent_lookup: Mapping[str, float] | None) -> float:
    """Return auxiliary patent count for a compound from PubChemLite lookup."""
    if not patent_lookup:
        return 0.0

    for column in ["Inchikey_std", "InChIKey", "Inchikey"]:
        value = row.get(column)
        if legacy__is_nullish(value):
            continue
        key = str(value).strip().upper()
        if key in patent_lookup:
            return float(patent_lookup[key])
    return 0.0


def legacy__extract_exposure_inputs(
    row: pd.Series,
    db_extract_col: str,
    patent_lookup: Mapping[str, float] | None = None,
    official_production_selections: Mapping[str, Mapping[str, Any]] | None = None,
    exposure_scale_selections: Mapping[str, Mapping[str, Any]] | None = None,
    patent_audit_records: Mapping[str, Mapping[str, Any]] | None = None,
    pubmed_query_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    slim = legacy__safe_json_loads(row.get(db_extract_col))
    exposure = slim.get("exposure") if isinstance(slim, dict) else {}
    exposure = exposure if isinstance(exposure, dict) else {}

    production = exposure.get("production") if isinstance(exposure.get("production"), dict) else {}
    patent = exposure.get("patent") if isinstance(exposure.get("patent"), dict) else {}
    literature = exposure.get("literature") if isinstance(exposure.get("literature"), dict) else {}

    inchikey = ""
    for column in ("Inchikey_std", "InChIKey", "Inchikey"):
        value = row.get(column)
        if legacy__is_nullish(value):
            continue
        inchikey = str(value).strip().upper()
        if inchikey:
            break
    official_decision = (
        official_production_selections.get(inchikey)
        if inchikey and official_production_selections
        else None
    )
    legacy_production_resolution = official_resolve_production_selection(production, official_decision)
    legacy_selected_production = legacy_production_resolution.get("selected_record") or {}

    if inchikey and exposure_scale_selections is not None:
        scale_resolution = dict(exposure_scale_selections.get(inchikey) or {})
        scale_fields = dict(scale_resolution.get("summary_fields") or {})
    else:
        scale_resolution = (
            legacy_production_resolution.get("audit") or legacy_production_resolution
        )
        selected_source = legacy_selected_production.get("source")
        selected_value = legacy__as_float(legacy_selected_production.get("selected_tonnes"))
        scale_fields = {
            "Exposure_scale_value_tonnes": selected_value,
            "Exposure_scale_lower_tonnes": selected_value,
            "Exposure_scale_upper_tonnes": selected_value,
            "Exposure_scale_source": selected_source,
            "Exposure_scale_source_id": selected_source,
            "Exposure_scale_metric_type": "production_volume" if legacy_selected_production else None,
            "Exposure_scale_activity": legacy_selected_production.get("scope"),
            "Exposure_scale_jurisdiction": legacy_selected_production.get("jurisdiction"),
            "Exposure_scale_reporting_period": legacy_selected_production.get("reporting_year"),
            "Exposure_scale_value_status": legacy_selected_production.get("volume_status"),
            "Exposure_scale_market_presence": (
                "confirmed_positive_quantity"
                if selected_value is not None and selected_value > 0
                else "confirmed_zero_quantity"
                if selected_value == 0
                else "unknown"
            ),
            "Exposure_scale_has_numeric": int(selected_value is not None),
            "Exposure_scale_has_production_numeric": int(selected_value is not None),
            "Exposure_scale_has_market_use_numeric": 0,
            "Exposure_scale_evidence_count": int(selected_value is not None),
            "Exposure_scale_numeric_evidence_count": int(selected_value is not None),
            "Exposure_scale_eligible_numeric_count": int(selected_value is not None),
            "Exposure_scale_source_count": int(bool(selected_source)),
            "Exposure_scale_numeric_source_count": int(bool(selected_source)),
            "Exposure_scale_source_url": None,
            "Exposure_scale_dataset_url": None,
            "Exposure_scale_record_id": None,
            "Exposure_scale_audit_relative_path": None,
            "Exposure_scale_selection_policy": legacy_production_resolution.get("policy_version"),
            "Exposure_scale_selection_reason": (
                "legacy_production_selection"
                if legacy_selected_production
                else "no_eligible_numeric_evidence"
            ),
        }
    # The production/market indicator is intentionally a single score component.
    # When standardized multi-source evidence is available, its historical maximum
    # is the scoring record. The legacy official-only decision remains in the audit
    # for backward traceability, but it no longer overrides a larger older/source value.
    selected_production = scale_resolution.get("selected_record") or legacy_selected_production
    production_resolution = scale_resolution or (
        legacy_production_resolution.get("audit") or legacy_production_resolution
    )
    prod_total = legacy__as_float(selected_production.get("selected_tonnes")) or 0.0
    reporting_year = selected_production.get("reporting_year") or selected_production.get("reporting_period")
    if not legacy__is_nullish(reporting_year):
        try:
            reporting_year = str(int(float(reporting_year)))
        except (TypeError, ValueError):
            reporting_year = str(reporting_year)
    patent_count_from_extract = legacy__max_numeric_from_nested(patent)
    patent_count_from_pubchemlite = legacy__lookup_patent_count(row, patent_lookup)
    litchemplast_count = legacy__max_numeric_from_nested(literature)
    patent_resolution = external_resolve_patent_selection(
        patent_count_from_extract,
        patent_count_from_pubchemlite,
        patent_audit_records.get(inchikey) if inchikey and patent_audit_records else None,
    )
    literature_query = external_build_literature_query_audit(
        litchemplast_count,
        pubmed_query_records.get(inchikey) if inchikey and pubmed_query_records else None,
    )

    fccmigex_listed = legacy__truthy_indicator(row.get("db_FCCmigex"))
    fcchumon_s1_listed = legacy__truthy_indicator(row.get("db_FCChumon_S1"))
    fcchumon_s2_listed = legacy__truthy_indicator(row.get("db_FCChumon_S2"))
    fcchumon_resolution = (
        slim.get("fcchumon_resolution")
        if isinstance(slim, dict) and isinstance(slim.get("fcchumon_resolution"), dict)
        else {}
    )
    fcchumon_resolution_available = (
        fcchumon_resolution.get("policy_version")
        == FCCHUMON_HUMAN_DETECTION_POLICY_VERSION
    )
    fcchumon_detected = bool(
        fcchumon_resolution_available and fcchumon_resolution.get("detected") is True
    )
    fcchumon_source_sheet = str(fcchumon_resolution.get("source_sheet") or "")
    fcchumon_s1_detected = int(
        fcchumon_detected and fcchumon_source_sheet == "FCChumon_S1"
    )
    fcchumon_s2_detected = int(
        fcchumon_detected and fcchumon_source_sheet == "FCChumon_S2"
    )
    fcchumon_detection_count = (
        max(0, int(legacy__as_float(fcchumon_resolution.get("detection_count")) or 0))
        if fcchumon_resolution_available
        else 0
    )
    inventory_count = legacy__as_float(row.get("GIC_inventory_listing_count"))
    if inventory_count is not None:
        inventory_count = max(0.0, inventory_count)
        if inventory_count.is_integer():
            inventory_count = int(inventory_count)
    inventory_status_value = row.get("GIC_inventory_data_status")
    inventory_data_status = (
        str(inventory_status_value).strip().lower()
        if not legacy__is_nullish(inventory_status_value)
        else ("available" if inventory_count is not None else "unavailable")
    )
    if inventory_data_status not in {"available", "not_queried", "unavailable"}:
        inventory_data_status = "unavailable"
    inventory_tags_value = row.get("GIC_inventory_list_tags")
    inventory_list_tags = "" if legacy__is_nullish(inventory_tags_value) else str(inventory_tags_value).strip()

    return {
        **{column: scale_fields.get(column) for column in legacy_EXPOSURE_SCALE_OUTPUT_COLUMNS},
        "Exposure_prod_total_tons": prod_total,
        "Exposure_prod_source": selected_production.get("source_name") or selected_production.get("source"),
        "Exposure_prod_jurisdiction": selected_production.get("jurisdiction"),
        "Exposure_prod_reporting_year": reporting_year,
        "Exposure_prod_value_status": selected_production.get("value_status") or selected_production.get("volume_status"),
        "Exposure_production_data_status": (
            "available"
            if rules_production_market_data_available(
                scale_fields.get("Exposure_scale_value_tonnes"),
                scale_fields.get("Exposure_scale_market_presence"),
            )
            else "unavailable"
        ),
        "Exposure_patent_count": patent_resolution["selected_count"],
        "Exposure_patent_data_status": (
            "available"
            if (patent_resolution.get("audit") or {}).get("selected_source")
            else "unavailable"
        ),
        "Exposure_patent_source": (patent_resolution.get("audit") or {}).get("selected_source"),
        "Exposure_patent_policy": external_PATENT_POLICY_VERSION,
        "Exposure_litchemplast_count": litchemplast_count,
        "Exposure_pubmed_title_abstract_count": literature_query["pubmed_query_count"],
        "Exposure_literature_count": literature_query["selected_count"],
        "Exposure_literature_data_status": literature_query["data_status"],
        "Exposure_literature_source": literature_query["selected_source"],
        "Exposure_literature_policy": literature_query["policy_version"],
        "Exposure_FCCmigex_listed": fccmigex_listed,
        "Exposure_food_contact_data_status": "available",
        "Exposure_FCChumon_S1_listed": fcchumon_s1_listed,
        "Exposure_FCChumon_S2_listed": fcchumon_s2_listed,
        "Exposure_FCChumon_S1_detected": fcchumon_s1_detected,
        "Exposure_FCChumon_S2_detected": fcchumon_s2_detected,
        "Exposure_FCChumon_detection_count": fcchumon_detection_count,
        "Exposure_FCChumon_detection_data_status": (
            "available" if fcchumon_resolution_available else "unavailable"
        ),
        "Exposure_FCChumon_detection_match_method": (
            fcchumon_resolution.get("match_method")
            if fcchumon_resolution_available
            else None
        ),
        "Exposure_FCChumon_detection_policy": (
            FCCHUMON_HUMAN_DETECTION_POLICY_VERSION
            if fcchumon_resolution_available
            else None
        ),
        "Exposure_inventory_listing_count": inventory_count,
        "Exposure_inventory_list_tags": inventory_list_tags,
        "Exposure_inventory_data_status": inventory_data_status,
        "raw_exposure": exposure,
        "auxiliary_exposure": {
            "pubchemlite_patent_count": patent_count_from_pubchemlite,
        },
        "production_selection": production_resolution,
        "production_market_scale_selection": scale_resolution,
        "legacy_official_production_selection": (
            legacy_production_resolution.get("audit") or legacy_production_resolution
        ),
        "patent_selection": patent_resolution.get("audit") or {},
        "literature_query_audit": literature_query.get("audit") or {},
        "fcchumon_detection_resolution": fcchumon_resolution,
    }


def legacy__score_exposure_inputs(
    inputs: dict[str, Any],
    max_total_score: float | None = None,
) -> dict[str, Any]:
    food_contact_score = 1.0 if inputs["Exposure_FCCmigex_listed"] else 0.0
    human_biomonitoring_score = (
        1.0
        if inputs["Exposure_FCChumon_S1_detected"]
        or inputs["Exposure_FCChumon_S2_detected"]
        else 0.0
    )
    inventory_component_score = rules_inventory_score(
        inputs.get("Exposure_inventory_listing_count"),
        inputs.get("Exposure_inventory_data_status"),
    )
    production_component_score = rules_production_market_score(
        inputs.get("Exposure_scale_value_tonnes"),
        inputs.get("Exposure_scale_market_presence"),
    )
    patent_component_score = rules_patent_score(
        inputs.get("Exposure_patent_count"),
    )
    literature_component_score = rules_literature_score(
        inputs.get("Exposure_literature_count"),
    )

    component_scores = {
        "food_contact": food_contact_score,
        "human_biomonitoring": human_biomonitoring_score,
        "inventory_presence_proxy": inventory_component_score,
        "production": production_component_score,
        "patent": patent_component_score,
        "literature": literature_component_score,
    }
    uncapped_total = sum(component_scores.values())
    total = (
        min(float(max_total_score), uncapped_total)
        if max_total_score is not None
        else uncapped_total
    )
    nonzero_basis = [name for name, score in component_scores.items() if score > 0]

    return {
        "Exposure_food_contact_score": food_contact_score,
        "Exposure_human_biomonitoring_score": human_biomonitoring_score,
        "Exposure_inventory_score": inventory_component_score,
        "Exposure_production_score": production_component_score,
        "Exposure_patent_score": patent_component_score,
        "Exposure_literature_score": literature_component_score,
        "Exposure_score": total,
        "Exposure_score_basis": "|".join(nonzero_basis) if nonzero_basis else None,
        "component_scores": component_scores,
        "uncapped_total": uncapped_total,
        "cap_applied": max_total_score is not None and uncapped_total > total,
    }


def legacy_add_exposure_columns(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
    patent_lookup: Mapping[str, float] | None = None,
    official_production_selections: Mapping[str, Mapping[str, Any]] | None = None,
    exposure_scale_selections: Mapping[str, Mapping[str, Any]] | None = None,
    patent_audit_records: Mapping[str, Mapping[str, Any]] | None = None,
    pubmed_query_records: Mapping[str, Mapping[str, Any]] | None = None,
    max_total_score: float | None = None,
    show_progress: bool = True,
) -> pd.DataFrame:
    """Add exposure input, score, basis, and JSON evidence columns."""
    output_values: dict[str, list[Any]] = {column: [] for column in legacy_EXPOSURE_OUTPUT_COLUMNS}

    iterator = range(len(agg_table))
    if show_progress and tqdm is not None:
        iterator = tqdm(iterator, desc="Computing exposure scores", unit="compound")

    for i in iterator:
        row = agg_table.iloc[i]
        inputs = legacy__extract_exposure_inputs(
            row,
            db_extract_col=db_extract_col,
            patent_lookup=patent_lookup,
            official_production_selections=official_production_selections,
            exposure_scale_selections=exposure_scale_selections,
            patent_audit_records=patent_audit_records,
            pubmed_query_records=pubmed_query_records,
        )
        scoring = legacy__score_exposure_inputs(inputs, max_total_score=max_total_score)
        evidence = {
            "inputs": {
                k: v
                for k, v in inputs.items()
                if k not in {
                    "raw_exposure",
                    "auxiliary_exposure",
                    "production_selection",
                    "production_market_scale_selection",
                    "legacy_official_production_selection",
                    "patent_selection",
                    "literature_query_audit",
                    "fcchumon_detection_resolution",
                }
            },
            "component_scores": scoring["component_scores"],
            "uncapped_total": scoring["uncapped_total"],
            "cap_applied": scoring["cap_applied"],
            "max_total_score": max_total_score,
            "exposure_scoring_policy_version": rules_EXPOSURE_SCORING_POLICY_VERSION,
            "exposure_theoretical_max_score": rules_EXPOSURE_TOTAL_MAX_SCORE,
            "inventory_scoring_policy_version": rules_INVENTORY_SCORING_POLICY_VERSION,
            "inventory_score_thresholds": rules_INVENTORY_SCORE_THRESHOLDS,
            "production_scoring_policy_version": rules_PRODUCTION_SCORING_POLICY_VERSION,
            "patent_scoring_policy_version": rules_PATENT_SCORING_POLICY_VERSION,
            "literature_scoring_policy_version": rules_LITERATURE_SCORING_POLICY_VERSION,
            "raw_exposure": inputs.get("raw_exposure") or {},
            "auxiliary_exposure": inputs.get("auxiliary_exposure") or {},
            "production_selection": inputs.get("production_selection") or {},
            "production_market_scale_selection": inputs.get("production_market_scale_selection") or {},
            "legacy_official_production_selection": inputs.get(
                "legacy_official_production_selection"
            ) or {},
            "patent_selection": inputs.get("patent_selection") or {},
            "literature_query_audit": inputs.get("literature_query_audit") or {},
            "fcchumon_detection_resolution": inputs.get(
                "fcchumon_detection_resolution"
            ) or {},
        }

        for column in legacy_EXPOSURE_OUTPUT_COLUMNS:
            if column == "Exposure_evidence":
                output_values[column].append(legacy__json_dumps_compact(evidence))
            elif column in inputs:
                output_values[column].append(inputs[column])
            else:
                output_values[column].append(scoring.get(column))

    for column, values in output_values.items():
        agg_table[column] = values
    return agg_table


