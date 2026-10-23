"""Stage 5A persistence and mobility with separate historical and isolated analysis views.

Value and selection rules retain the historical implementations fingerprinted in
hazard_policy.json. No bioaccumulation, toxicity or aggregate score is calculated.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json
import math
from pathlib import Path
import platform
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .inputs import _file_hash
from .evidence import _json, _read_csv
from .evidence_specialists import require_prediction_isolation
from .lrtp import _verify_outputs

DEFAULT_POLICY = Path(__file__).with_name("hazard_policy.json")
POLICY_HASH = _file_hash(DEFAULT_POLICY)
POLICY = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
HAZARD_SOURCE_SELECTION_POLICY_VERSION = POLICY["constants"]["HAZARD_SOURCE_SELECTION_POLICY_VERSION"]
HAZARD_SOURCE_SELECTION_RULE = POLICY["constants"]["HAZARD_SOURCE_SELECTION_RULE"]
PERSISTENCE_VEGA_COLUMNS = POLICY["constants"]["PERSISTENCE_VEGA_COLUMNS"]
OPERA_KOC_COLUMNS = POLICY["constants"]["OPERA_KOC_COLUMNS"]
LRTP_COLUMNS = POLICY["constants"]["LRTP_COLUMNS"]
LRTP_VALID_STATUSES = POLICY["constants"]["LRTP_VALID_STATUSES"]
LRTP_CTD_LIMIT_KM = POLICY["constants"]["LRTP_CTD_LIMIT_KM"]
LRTP_TE_LIMIT_PERCENT = POLICY["constants"]["LRTP_TE_LIMIT_PERCENT"]
OUTPUT_COLUMNS = POLICY['output_columns']
SCORE_COLUMNS = ['Persistence_score', 'Aquatic_M_score', 'LRTP_M_score', 'Mobility_score']
QSAR_FIELDS = [c for columns in PERSISTENCE_VEGA_COLUMNS.values() for c in columns] + list(OPERA_KOC_COLUMNS.values())
INPUT_FIELDS = QSAR_FIELDS + list(LRTP_COLUMNS.values())
NUMERIC_INPUTS = [columns[1] for columns in PERSISTENCE_VEGA_COLUMNS.values()] + [OPERA_KOC_COLUMNS['logkoc'], OPERA_KOC_COLUMNS['adi'], LRTP_COLUMNS['ctd'], LRTP_COLUMNS['te']]
tqdm = None

def select_independent_first(
    *,
    independent_score: Optional[float],
    independent_basis: Optional[str],
    curated_score: Optional[float],
    curated_basis: Optional[str],
) -> tuple[Optional[float], Optional[str], dict[str, Any]]:
    """Select an independent score before a curated fallback.

    ``is not None`` is intentional: a reliable independent score of zero is
    evidence-supported and must take precedence over curated evidence.
    """

    if independent_score is not None:
        score = independent_score
        basis = independent_basis
        source_class = "independent_computation"
        fallback_reason = None
    elif curated_score is not None:
        score = curated_score
        basis = curated_basis
        source_class = "curated_fallback"
        fallback_reason = "independent_score_unavailable_or_unreliable"
    else:
        score = None
        basis = None
        source_class = "unavailable"
        fallback_reason = "no_usable_independent_or_curated_score"

    evidence = {
        "policy_version": HAZARD_SOURCE_SELECTION_POLICY_VERSION,
        "selection_rule": HAZARD_SOURCE_SELECTION_RULE,
        "independent_candidate": {
            "score": independent_score,
            "basis": independent_basis,
        },
        "curated_candidate": {
            "score": curated_score,
            "basis": curated_basis,
        },
        "selected": {
            "score": score,
            "basis": basis,
            "source_class": source_class,
        },
        "fallback_reason": fallback_reason,
    }
    return score, basis, evidence


def _is_nullish(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _safe_json_loads(x: Any) -> Optional[dict]:
    if _is_nullish(x):
        return None
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x)
    except Exception:
        return None


def _json_default(o: Any) -> Any:
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


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _as_float(v: Any) -> Optional[float]:
    if _is_nullish(v):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _get_compound_key(row: pd.Series, idx: int) -> str:
    return (
        row.get("Inchikey_std")
        or row.get("InChIKey")
        or row.get("CAS")
        or f"row_{idx}"
    )


def _extract_core_label(assessment: Any) -> Optional[str]:
    """
    Convert VEGA labels such as "nP (GOOD reliability)" to "nP".
    """
    if _is_nullish(assessment):
        return None
    s = str(assessment).strip()
    if s == "[Error]":
        return None
    for sep in [" (", "("]:
        if sep in s:
            s = s.split(sep, 1)[0].strip()
            break
    return s if s else None


def _map_label_to_score(core):
    return POLICY['persistence_labels'].get(core.strip()) if core else None


def _pick_curated_db_p(slim: dict) -> Tuple[Optional[float], Optional[str], dict]:
    """
    Read curated persistence evidence from `db_extract_info.hazard.P`.

    Returns:
        tuple: (score, basis database, evidence dictionary).
    """
    hz = slim.get("hazard") or {}
    p_block = hz.get("P")
    evidence = {"curated_db": {"selected": None, "all": {}}}

    if not isinstance(p_block, dict) or not p_block:
        return None, None, evidence

    for db, vals in p_block.items():
        if isinstance(vals, list) and vals:
            unique_vals = []
            for x in vals:
                if x not in unique_vals:
                    unique_vals.append(x)
            evidence["curated_db"]["all"][db] = unique_vals[:5]

    db_order = ["PlastChem"] + sorted([d for d in p_block.keys() if d != "PlastChem"])
    for db in db_order:
        vals = p_block.get(db)
        if not (isinstance(vals, list) and vals):
            continue

        chosen_raw = None
        chosen_score = None

        for x in vals:
            f = _as_float(x)
            if f is not None:
                chosen_raw = x
                chosen_score = f
                break

        if chosen_score is None:
            for x in vals:
                core = _extract_core_label(x)
                mapped = _map_label_to_score(core)
                if mapped is not None:
                    chosen_raw = x
                    chosen_score = mapped
                    break

        if chosen_score is not None:
            evidence["curated_db"]["selected"] = {
                "db": db,
                "raw": chosen_raw,
                "score": chosen_score,
            }
            return chosen_score, db, evidence

    return None, None, evidence


def _compute_vega_p(
    row: pd.Series,
    adi_threshold: float = 0.5,
    agg_rule: str = "max",
) -> Tuple[Optional[float], dict]:
    """
    Compute persistence from VEGA IRFMN assessment and ADI columns.
    """
    evidence = {
        "qsar_vega_irfmn": {
            "adi_threshold": adi_threshold,
            "compartments": {},
            "aggregation": {},
        }
    }
    scores = []
    scored_compartments = []

    for comp, (assessment_col, adi_col) in PERSISTENCE_VEGA_COLUMNS.items():
        if assessment_col not in row.index and adi_col not in row.index:
            continue

        assessment = row.get(assessment_col)
        adi = row.get(adi_col)
        adi_f = _as_float(adi)
        core = _extract_core_label(assessment)
        mapped = _map_label_to_score(core)

        usable = True
        reason = None
        if mapped is None:
            usable = False
            reason = "missing_or_unrecognized_label"
        elif adi_f is None:
            usable = False
            reason = "missing_ADI"
        elif adi_f < adi_threshold:
            usable = False
            reason = f"adi_below_threshold({adi_f}<{adi_threshold})"

        evidence["qsar_vega_irfmn"]["compartments"][comp] = {
            "assessment": None if _is_nullish(assessment) else str(assessment),
            "core_label": core,
            "mapped_score": mapped,
            "adi": adi_f,
            "usable": usable,
            "exclude_reason": reason,
        }

        if usable and mapped is not None:
            scores.append(mapped)
            scored_compartments.append(comp)

    final = None
    if scores:
        if agg_rule != "max":
            agg_rule = "max"
        final = max(scores)
        picked = scored_compartments[scores.index(final)]
        evidence["qsar_vega_irfmn"]["aggregation"] = {
            "rule": agg_rule,
            "picked_compartment": picked,
        }
    else:
        evidence["qsar_vega_irfmn"]["aggregation"] = {
            "rule": agg_rule,
            "picked_compartment": None,
        }

    return final, evidence


def build_persistence_audit_records(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
) -> list[dict[str, Any]]:
    """Build compound-level persistence evidence records for audit export."""
    records = []

    for idx in range(len(agg_table)):
        row = agg_table.iloc[idx]
        slim = _safe_json_loads(row.get(db_extract_col))
        if not isinstance(slim, dict):
            continue

        identity = slim.get("identity") or {}
        hazard = slim.get("hazard") or {}
        mismatch = slim.get("mismatch_report") or []
        p_db = hazard.get("P")

        vega_block = {}
        for assessment_col, adi_col in PERSISTENCE_VEGA_COLUMNS.values():
            for col in [assessment_col, adi_col]:
                if col in agg_table.columns and not _is_nullish(row.get(col)):
                    vega_block[col] = row.get(col)

        sources = {}
        if isinstance(identity, dict) and isinstance(identity.get("_sources"), dict):
            sources["identity"] = identity["_sources"]
        if isinstance(p_db, dict) and p_db:
            sources["hazard.P"] = sorted(p_db.keys())

        records.append(
            {
                "compound_key": _get_compound_key(row, idx),
                "identity": {
                    k: identity.get(k)
                    for k in ["inchikey", "cas", "name", "smiles", "formula", "monoisotopic_mass"]
                    if k in identity
                },
                "persistence_from_db_extract": p_db if isinstance(p_db, dict) else None,
                "persistence_from_vega": vega_block,
                "sources": sources,
                "mismatch_report": mismatch,
            }
        )

    return records


def add_persistence_columns(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
    out_score_col: str = "Persistence_score",
    out_basis_col: str = "Persistence_score_basis",
    out_evidence_col: str = "Persistence_evidence",
    adi_threshold: float = 0.5,
    vega_agg_rule: str = "max",
    show_progress: bool = False,
) -> pd.DataFrame:
    """
    Add persistence score, basis, and JSON evidence columns.

    Priority:
        1. VEGA IRFMN persistence assessment with ADI filtering.
        2. Curated database evidence from `db_extract_info.hazard.P` as fallback.
    """
    scores = []
    bases = []
    evidences = []

    iterator = range(len(agg_table))
    if show_progress and tqdm is not None:
        iterator = tqdm(iterator, desc="Computing persistence scores", unit="compound")

    for i in iterator:
        row = agg_table.iloc[i]
        slim = _safe_json_loads(row.get(db_extract_col))
        evidence: Dict[str, Any] = {}

        db_score, db_basis, ev_db = (None, None, {"curated_db": {"selected": None, "all": {}}})
        if isinstance(slim, dict):
            db_score, db_basis, ev_db = _pick_curated_db_p(slim)
        evidence.update(ev_db)

        vega_score, ev_vega = _compute_vega_p(
            row,
            adi_threshold=adi_threshold,
            agg_rule=vega_agg_rule,
        )
        evidence.update(ev_vega)

        final_score, final_basis, final_selection = select_independent_first(
            independent_score=vega_score,
            independent_basis="VEGA(IRFMN)" if vega_score is not None else None,
            curated_score=db_score,
            curated_basis=(db_basis or "CuratedDB") if db_score is not None else None,
        )
        evidence["final_selection"] = final_selection

        scores.append(final_score)
        bases.append(final_basis)
        evidences.append(_json_dumps(evidence))

    agg_table[out_score_col] = scores
    agg_table[out_basis_col] = bases
    agg_table[out_evidence_col] = evidences
    return agg_table


def _json_dumps_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _pick_curated_db_mobility(slim: dict) -> Tuple[Optional[float], Optional[str], dict]:
    """Read curated mobility evidence from `db_extract_info.hazard.M`."""
    hazard = slim.get("hazard") or {}
    m_block = hazard.get("M")
    evidence = {"curated_db": {"selected": None, "all": {}}}

    if not isinstance(m_block, dict) or not m_block:
        return None, None, evidence

    for db, vals in m_block.items():
        if isinstance(vals, list) and vals:
            unique_vals = []
            for x in vals:
                if x not in unique_vals:
                    unique_vals.append(x)
            evidence["curated_db"]["all"][db] = unique_vals[:5]

    db_order = ["PlastChem"] + sorted([d for d in m_block.keys() if d != "PlastChem"])
    for db in db_order:
        vals = m_block.get(db)
        if not (isinstance(vals, list) and vals):
            continue
        for x in vals:
            score = _as_float(x)
            if score is not None:
                evidence["curated_db"]["selected"] = {"db": db, "raw": x, "score": score}
                return score, db, evidence

    return None, None, evidence


def _opera_logkoc_to_mobility_score(logkoc):
    for interval in POLICY['aquatic_bins']:
        if logkoc < interval['upper_exclusive']:
            return interval['score']
    return 0.0


def _compute_opera_mobility_from_row(
    row: pd.Series,
    adi_threshold: float = 0.5,
) -> Tuple[Optional[float], dict]:
    """Compute aquatic mobility from OPERA Koc columns using strict ADI filtering."""
    logkoc = _as_float(row.get(OPERA_KOC_COLUMNS["logkoc"]))
    adi = _as_float(row.get(OPERA_KOC_COLUMNS["adi"]))
    assessment = row.get(OPERA_KOC_COLUMNS["assessment"])

    evidence = {
        "qsar_opera_koc": {
            "logKoc": logkoc,
            "adi": adi,
            "adi_threshold": adi_threshold,
            "assessment_raw": None if _is_nullish(assessment) else str(assessment),
            "usable": False,
            "exclude_reason": None,
            "pathway": "water",
            "basis": "aquatic(OPERA logKoc)",
            "mapping": (
                "logKoc->Aquatic_M_score bins: <2=2 (CLP vM), "
                "2-3=1 (CLP M), 3-4=0.5 (internal near-mobile), >=4=0"
            ),
        }
    }

    if logkoc is None:
        evidence["qsar_opera_koc"]["exclude_reason"] = "missing_logKoc"
        return None, evidence
    if adi is None:
        evidence["qsar_opera_koc"]["exclude_reason"] = "missing_adi"
        return None, evidence
    if adi < adi_threshold:
        evidence["qsar_opera_koc"]["exclude_reason"] = f"adi_below_threshold({adi}<{adi_threshold})"
        return None, evidence

    score = _opera_logkoc_to_mobility_score(logkoc)
    evidence["qsar_opera_koc"]["usable"] = True
    evidence["qsar_opera_koc"]["aquatic_mobility_score"] = score
    evidence["qsar_opera_koc"]["Aquatic_M_score"] = score
    evidence["qsar_opera_koc"]["mobility_score"] = score
    return score, evidence


def _lrtp_ratio_to_mobility_score(ratio):
    for interval in POLICY['lrtp_bins']:
        if ratio >= interval['lower_inclusive']:
            return interval['score']
    return 0.0


def _compute_lrtp_mobility_from_row(row: pd.Series) -> Tuple[Optional[float], dict]:
    """Compute LRTP mobility from OECD CTD and TE outputs."""
    ctd_km = _as_float(row.get(LRTP_COLUMNS["ctd"]))
    te_percent = _as_float(row.get(LRTP_COLUMNS["te"]))
    raw_status = row.get(LRTP_COLUMNS["status"])
    status = None if _is_nullish(raw_status) else str(raw_status).strip().lower()
    warning_flags = row.get(LRTP_COLUMNS["warning_flags"])
    ctd_ratio = None if ctd_km is None else ctd_km / LRTP_CTD_LIMIT_KM
    te_ratio = None if te_percent is None else te_percent / LRTP_TE_LIMIT_PERCENT
    lrtp_ratio = max([value for value in [ctd_ratio, te_ratio] if value is not None], default=None)

    evidence = {
        "oecd_lrtp": {
            "CTD_km": ctd_km,
            "TE_percent": te_percent,
            "input_status": status,
            "warning_flags": None if _is_nullish(warning_flags) else str(warning_flags),
            "usable": False,
            "exclude_reason": None,
            "pathway": "long_range_transport",
            "basis": "LRTP(OECD CTD/TE)",
            "criteria": {
                "CTD_limit_km": LRTP_CTD_LIMIT_KM,
                "TE_limit_percent": LRTP_TE_LIMIT_PERCENT,
            },
            "ratios": {
                "CTD_ratio": ctd_ratio,
                "TE_ratio": te_ratio,
                "max_ratio": lrtp_ratio,
            },
            "mapping": (
                "max(CTD/5096.73, TE/2.2476)->LRTP_M_score bins: "
                "<0.25=0, 0.25-0.5=0.5, 0.5-1=1, >=1=2"
            ),
        }
    }

    if ctd_km is None or te_percent is None:
        evidence["oecd_lrtp"]["exclude_reason"] = "missing_CTD_or_TE"
        return None, evidence
    if status not in LRTP_VALID_STATUSES:
        evidence["oecd_lrtp"]["exclude_reason"] = f"unusable_input_status({status})"
        return None, evidence

    assert lrtp_ratio is not None
    score = _lrtp_ratio_to_mobility_score(lrtp_ratio)
    evidence["oecd_lrtp"]["usable"] = True
    evidence["oecd_lrtp"]["LRTP_M_score"] = score
    evidence["oecd_lrtp"]["mobility_score"] = score
    return score, evidence


def _format_max_mobility_basis(candidates: list[dict[str, Any]]) -> Optional[str]:
    if not candidates:
        return None
    max_score = max(candidate["score"] for candidate in candidates)
    winning_bases = [
        str(candidate["basis"])
        for candidate in candidates
        if candidate["score"] == max_score and not _is_nullish(candidate.get("basis"))
    ]
    if not winning_bases:
        return None
    return "max: " + "+".join(winning_bases)


def build_mobility_audit_records(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
) -> list[dict[str, Any]]:
    """Build compound-level mobility evidence records for audit export."""
    records = []
    for idx in range(len(agg_table)):
        row = agg_table.iloc[idx]
        slim = _safe_json_loads(row.get(db_extract_col))
        if not isinstance(slim, dict):
            continue
        identity = slim.get("identity") or {}
        hazard = slim.get("hazard") or {}
        m_block = hazard.get("M")
        opera_block = {
            col: row.get(col)
            for col in OPERA_KOC_COLUMNS.values()
            if col in agg_table.columns and not _is_nullish(row.get(col))
        }
        lrtp_block = {
            col: row.get(col)
            for col in LRTP_COLUMNS.values()
            if col in agg_table.columns and not _is_nullish(row.get(col))
        }
        records.append(
            {
                "compound_key": _get_compound_key(row, idx),
                "identity": {k: identity.get(k) for k in ["inchikey", "cas", "name", "smiles"] if k in identity},
                "mobility_from_db_extract_reference": m_block if isinstance(m_block, dict) else None,
                "mobility_from_opera": opera_block,
                "mobility_from_lrtp": lrtp_block,
                "mismatch_report": slim.get("mismatch_report") or [],
            }
        )
    return records


def add_mobility_columns(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
    out_aquatic_score_col: str = "Aquatic_M_score",
    out_lrtp_score_col: str = "LRTP_M_score",
    out_score_col: str = "Mobility_score",
    out_basis_col: str = "Mobility_score_basis",
    out_evidence_col: str = "Mobility_evidence",
    adi_threshold: float = 0.5,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Add mobility score, basis, and JSON evidence columns."""
    aquatic_scores = []
    lrtp_scores = []
    scores = []
    bases = []
    evidences = []

    iterator = range(len(agg_table))
    if show_progress and tqdm is not None:
        iterator = tqdm(iterator, desc="Computing mobility scores", unit="compound")

    for i in iterator:
        row = agg_table.iloc[i]
        slim = _safe_json_loads(row.get(db_extract_col))
        evidence: Dict[str, Any] = {}

        db_score, db_basis, ev_db = (None, None, {"curated_db": {"selected": None, "all": {}}})
        if isinstance(slim, dict):
            db_score, db_basis, ev_db = _pick_curated_db_mobility(slim)
        evidence.update(ev_db)
        if db_score is not None:
            evidence["curated_db"]["scoring_note"] = (
                "Curated mobility is eligible only as a fallback when neither "
                "the OPERA aquatic pathway nor the OECD LRTP pathway yields a "
                "usable independent score."
            )

        aquatic_score, ev_opera = _compute_opera_mobility_from_row(row, adi_threshold=adi_threshold)
        evidence.update(ev_opera)
        lrtp_score, ev_lrtp = _compute_lrtp_mobility_from_row(row)
        evidence.update(ev_lrtp)

        candidates = []
        if aquatic_score is not None:
            candidates.append(
                {
                    "source": "qsar_opera_koc",
                    "pathway": "aquatic",
                    "basis": "aquatic(OPERA logKoc)",
                    "score": aquatic_score,
                }
            )
        if lrtp_score is not None:
            candidates.append(
                {
                    "source": "oecd_lrtp",
                    "pathway": "long_range_transport",
                    "basis": "LRTP(OECD CTD/TE)",
                    "score": lrtp_score,
                }
            )

        if candidates:
            independent_score = max(candidate["score"] for candidate in candidates)
            independent_basis = _format_max_mobility_basis(candidates)
        else:
            independent_score = None
            independent_basis = None

        final_score, final_basis, final_selection = select_independent_first(
            independent_score=independent_score,
            independent_basis=independent_basis,
            curated_score=db_score,
            curated_basis=(db_basis or "CuratedDB") if db_score is not None else None,
        )
        evidence["final_mobility"] = {
            "score": final_score,
            "basis": final_basis,
            "Aquatic_M_score": aquatic_score,
            "LRTP_M_score": lrtp_score,
            "independent_score": independent_score,
            "independent_basis": independent_basis,
            "selection_rule": (
                "maximum across usable aquatic and LRTP pathways, followed by "
                "curated fallback only when both independent pathways are unavailable"
            ),
            "candidates": candidates,
            "source_selection": final_selection,
        }

        aquatic_scores.append(aquatic_score)
        lrtp_scores.append(lrtp_score)
        scores.append(final_score)
        bases.append(final_basis)
        evidences.append(_json_dumps_compact(evidence))

    agg_table[out_aquatic_score_col] = aquatic_scores
    agg_table[out_lrtp_score_col] = lrtp_scores
    agg_table[out_score_col] = scores
    agg_table[out_basis_col] = bases
    agg_table[out_evidence_col] = evidences
    return agg_table


def scoring_inputs(compounds, *, historical=False):
    """Project an explicit P/M input allowlist; annotation fields never reach the kernel."""
    required = ['inchikey', 'db_extract_info', *INPUT_FIELDS]
    if not historical:
        required += ['qsar_identity_status', 'qsar_identity_reason', 'qsar_evidence_available', 'lrtp_available']
    missing = set(required) - set(compounds.columns)
    if missing:
        raise ValueError('Missing P/M input columns: ' + ', '.join(sorted(missing)))
    if compounds['inchikey'].duplicated().any() or compounds['inchikey'].eq('').any():
        raise ValueError('P/M inputs require unique nonempty full chemical keys.')
    frame = compounds[['inchikey', 'db_extract_info', *INPUT_FIELDS]].copy()
    frame['Inchikey_std'] = frame['inchikey']
    if not historical:
        review = compounds['qsar_identity_status'].eq('review_required')
        flags = compounds[['qsar_evidence_available', 'lrtp_available']].astype(str)
        if not flags.isin(['True', 'False']).all().all():
            raise ValueError('P/M availability flags must be explicit booleans.')
        values = frame[QSAR_FIELDS + [LRTP_COLUMNS['ctd'], LRTP_COLUMNS['te']]]
        if values.loc[review].map(lambda v: not _is_nullish(v)).any().any() or flags.loc[review].ne('False').any().any():
            raise ValueError('Identity-review prediction leaked into P/M analysis.')
        frame.loc[flags['qsar_evidence_available'].eq('False'), QSAR_FIELDS] = None
        # Preserve diagnostic status and warnings even when numeric evidence is unavailable.
        frame.loc[flags['lrtp_available'].eq('False'), [LRTP_COLUMNS['ctd'], LRTP_COLUMNS['te']]] = None
    for column in NUMERIC_INPUTS:
        frame[column] = frame[column].map(_as_float)
        if frame[column].dropna().map(lambda v: not math.isfinite(v)).any():
            raise ValueError('Nonfinite numerical P/M input: ' + column)
    payloads = []
    for text in frame['db_extract_info']:
        payload = json.loads(text)
        if not isinstance(payload, dict) or not isinstance(payload.get('hazard', {}), dict):
            raise ValueError('P/M evidence must contain a valid hazard object.')
        # Identity and mismatch fields are audit context only; the scoring keys are P/M.
        payloads.append(_json({**{k: payload[k] for k in ['identity', 'mismatch_report'] if k in payload},
                               'hazard': {k: v for k, v in payload.get('hazard', {}).items() if k in ['P', 'M']}}))
    frame['db_extract_info'] = payloads
    return frame


def score_pm(compounds, *, historical=False):
    """Calculate P/M only; historical mode must be requested explicitly for validation."""
    frame = scoring_inputs(compounds, historical=historical)
    frame = add_persistence_columns(frame, adi_threshold=POLICY['adi_threshold'])
    frame = add_mobility_columns(frame, adi_threshold=POLICY['adi_threshold'])
    audits = {'persistence': build_persistence_audit_records(frame), 'mobility': build_mobility_audit_records(frame)}
    result = frame[['inchikey', *OUTPUT_COLUMNS]].copy()
    if not historical:
        for i, row in compounds.reset_index(drop=True).iterrows():
            if row['qsar_identity_status'] != 'review_required':
                continue
            context = {'status': 'review_required', 'reason': row['qsar_identity_reason'],
                       'prediction_exclusion_reason': 'identity_review_required'}
            p = json.loads(result.iloc[i]['Persistence_evidence'])
            for part in p['qsar_vega_irfmn']['compartments'].values():
                part['exclude_reason'] = 'identity_review_required'
            p['identity_review'] = context
            m = json.loads(result.iloc[i]['Mobility_evidence'])
            for part in ['qsar_opera_koc', 'oecd_lrtp']:
                m[part]['exclude_reason'] = 'identity_review_required'
            m['identity_review'] = context
            result.at[result.index[i], 'Persistence_evidence'] = _json(p)
            result.at[result.index[i], 'Mobility_evidence'] = _json(m)
            for audit in audits.values():
                audit[i]['identity_review'] = context
    return result, audits


def _aligned_history(base, qsar, lrtp):
    """Reconstruct historical model inputs from verified local Stage 3 artifacts only."""
    result = base.copy()
    for source, fields in [(qsar, QSAR_FIELDS), (lrtp, list(LRTP_COLUMNS.values()))]:
        if source['inchikey'].duplicated().any() or set(source['inchikey']) != set(base['inchikey']):
            raise ValueError('Historical P/M input identity sets differ from Stage 4C.')
        aligned = source.set_index('inchikey').loc[base['inchikey']]
        for column in fields:
            result[column] = aligned[column].to_numpy()
    return result


@dataclass
class HazardResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    impacts: pd.DataFrame
    summary: pd.DataFrame
    audits: dict
    manifest: dict

    def write_reports(self, output_dir):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in [('compound_pm_hazard', self.compounds), ('pm_historical', self.historical),
                            ('identity_review_pm_impacts', self.impacts), ('pm_summary', self.summary)]:
            path = folder / (name + '.csv')
            frame.to_csv(path, index=False, encoding='utf-8', lineterminator='\n')
            outputs[path.name] = _file_hash(path)
        for name, rows in self.audits.items():
            path = folder / (name + '.jsonl')
            with path.open('w', encoding='utf-8', newline='\n') as stream:
                for row in rows:
                    stream.write(_json(row) + '\n')
            outputs[path.name] = _file_hash(path)
        (folder / 'hazard_manifest.json').write_text(json.dumps({**self.manifest, 'output_sha256': outputs}, indent=2) + '\n', encoding='utf-8')


def integrate_pm_hazard(annotation_results, stage3_results=None):
    """Attach isolated P/M analysis and keep historical reproduction in separate reports."""
    annotations = Path(annotation_results)
    root = annotations.parent.parent
    stage3 = Path(stage3_results) if stage3_results is not None else root / 'stage3'
    paths = {'annotations': annotations / 'annotation_manifest.json',
             'specialists': annotations.parent / '4b' / 'specialist_manifest.json',
             'basic': annotations.parent / 'evidence_manifest.json',
             'qsar': stage3 / 'qsar_manifest.json', 'lrtp': stage3 / 'lrtp' / 'lrtp_manifest.json'}
    hashes = {name: _file_hash(path) for name, path in paths.items()}
    manifests = {name: json.loads(path.read_text(encoding='utf-8')) for name, path in paths.items()}
    if POLICY['schema_version'] != 1 or _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError('P/M policy changed; restart the process.')
    for name, path in paths.items():
        _verify_outputs(path.parent, manifests[name])
    if (manifests['annotations']['upstream_manifest_sha256'] != hashes['specialists'] or
        manifests['specialists']['upstream_manifest_sha256']['basic'] != hashes['basic'] or
        manifests['basic']['upstream_manifests_sha256']['qsar'] != hashes['qsar'] or
        manifests['basic']['upstream_manifests_sha256']['lrtp'] != hashes['lrtp'] or
        manifests['lrtp']['upstream_qsar_manifest_sha256'] != hashes['qsar']):
        raise ValueError('P/M input manifests refer to different upstream runs.')
    compounds = _read_csv(annotations / 'compound_annotated_evidence.csv')
    require_prediction_isolation(compounds)
    historical_inputs = _aligned_history(compounds, _read_csv(stage3 / 'compound_qsar.csv'),
                                         _read_csv(stage3 / 'lrtp' / 'lrtp_historical_results.csv'))
    historical, historical_audits = score_pm(historical_inputs, historical=True)
    analysis, analysis_audits = score_pm(compounds)
    result = compounds.copy()
    for column in OUTPUT_COLUMNS:
        result[column] = analysis[column].to_numpy()
    for dimension in ['Persistence', 'Mobility']:
        available = result[dimension + '_score'].notna()
        result[dimension.lower() + '_available'] = available
        result[dimension.lower() + '_unavailable_reason'] = [
            '' if usable else 'identity_review_required_no_curated_fallback' if status == 'review_required' else 'no_usable_evidence'
            for usable, status in zip(available, result['qsar_identity_status'])]
    require_prediction_isolation(result)
    historical['result_role'] = 'historical_reproduction_only'
    result['pm_result_role'] = 'analysis_after_identity_isolation'
    impacts = []
    for i in result.index[result['qsar_identity_status'].eq('review_required')]:
        row = result.loc[i]
        for column in OUTPUT_COLUMNS:
            before, after = historical.at[i, column], result.at[i, column]
            impacts.append({'inchikey': row['inchikey'], 'vega_row_no': row['vega_row_no'],
                            'identity_reason': row['qsar_identity_reason'], 'field': column,
                            'historical_value': before, 'analysis_value': after,
                            'changed': (None if _is_nullish(before) else before) != (None if _is_nullish(after) else after),
                            'reason': 'identity_review_required', 'gic_shared_identifier_tag_expansion': row['gic_shared_identifier_tag_expansion']})
    audits = {**{name + '_historical_audit': rows for name, rows in historical_audits.items()},
              **{name + '_analysis_audit': rows for name, rows in analysis_audits.items()}}
    with (annotations.parent / 'basic_evidence_audit.jsonl').open(encoding='utf-8') as stream:
        audits['pm_curated_source_links'] = [row for row in map(json.loads, stream) if row.get('field_path') in ['hazard.P', 'hazard.M']]
    with (annotations / 'identity_review_source_links.jsonl').open(encoding='utf-8') as stream:
        audits['identity_review_source_links'] = list(map(json.loads, stream))
    # Link each pathway to its frozen model definitions, report batch and source audit.
    decisions = []
    for i, row in result.iterrows():
        for dimension in ['Persistence', 'Mobility']:
            payload = json.loads(row[dimension + '_evidence'])
            selection = payload['final_selection'] if dimension == 'Persistence' else payload['final_mobility']['source_selection']
            decisions.append({'compound_key': row['inchikey'], 'dimension': dimension,
                              'qsar_inchikey': row['qsar_inchikey'], 'vega_row_no': row['vega_row_no'],
                              'qsar_manifest_sha256': hashes['qsar'], 'lrtp_manifest_sha256': hashes['lrtp'],
                              'basic_evidence_manifest_sha256': hashes['basic'],
                              'identity_status': row['qsar_identity_status'], 'identity_reason': row['qsar_identity_reason'],
                              'source_selection': selection, 'available': bool(pd.notna(row[dimension + '_score'])),
                              'unavailable_reason': row[dimension.lower() + '_unavailable_reason']})
    audits['pm_decisions'] = decisions
    summary = []
    for view, frame in [('historical', historical), ('analysis', result)]:
        for column in SCORE_COLUMNS:
            summary.append({'view': view, 'field': column, 'compounds': len(frame),
                            'available': int(frame[column].notna().sum()), 'unavailable': int(frame[column].isna().sum()),
                            'zero_scores': int(frame[column].eq(0).sum())})
    for name, path in paths.items():
        if _file_hash(path) != hashes[name]:
            raise ValueError('Upstream P/M manifest changed during scoring.')
        _verify_outputs(path.parent, manifests[name])
    if _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError('P/M policy changed during scoring.')
    counts = {'compounds': len(result), 'identity_review_compounds': int(result['qsar_identity_status'].eq('review_required').sum()),
              'identity_review_source_links': len(audits['identity_review_source_links']),
              'gic_name_review_required': int(result['gic_name_review_required'].eq('True').sum()),
              'gic_tag_expansion_review_required': int(result['gic_shared_identifier_tag_expansion'].eq('True').sum()),
              'persistence_available': int(result['persistence_available'].sum()), 'mobility_available': int(result['mobility_available'].sum())}
    manifest = {'schema_version': 1, 'scope': POLICY['scope'], 'policy_sha256': POLICY_HASH,
                'implementation_sha256': _file_hash(Path(__file__)), 'upstream_manifests_sha256': hashes,
                'qsar_model_mapping_sha256': _file_hash(Path(__file__).with_name('qsar_models.json')),
                'counts': counts, 'rules': POLICY['rules'], 'scoring_input_columns': INPUT_FIELDS,
                'scoring_evidence_paths': ['hazard.P', 'hazard.M'],
                'historical_sources': POLICY['historical_sources'],
                'runtime': {'python': platform.python_version(), 'pandas': pd.__version__}}
    return HazardResult(result, historical, pd.DataFrame(impacts), pd.DataFrame(summary), audits, manifest)
