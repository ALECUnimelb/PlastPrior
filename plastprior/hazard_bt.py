"""Stage 5B B/T screening with separate historical and identity-isolated views.

Historical kernels retain the source rules fingerprinted in hazard_bt_policy.json.
Only local inputs are used at runtime; the legacy project is not imported.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json
import math
from pathlib import Path
import platform
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
try:
    from rdkit import Chem, rdBase
except ImportError as exc:
    raise RuntimeError('Stage 5B requires RDKit. Install the pinned requirements in a supported Python environment before rerunning.') from exc

from .hazard import select_independent_first, POLICY_HASH as PM_POLICY_HASH
from .inputs import _file_hash
from .evidence import _json, _read_csv
from .evidence_specialists import require_prediction_isolation
from .lrtp import _verify_outputs

DEFAULT_POLICY = Path(__file__).with_name('hazard_bt_policy.json')
POLICY_HASH = _file_hash(DEFAULT_POLICY)
POLICY = json.loads(DEFAULT_POLICY.read_text(encoding='utf-8'))
BCF_MODELS = POLICY['constants']['BCF_MODELS']
TOXICITY_ENDPOINTS = POLICY['constants']['TOXICITY_ENDPOINTS']
STRUCTURAL_HALOGEN_BASIS = POLICY['constants']['STRUCTURAL_HALOGEN_BASIS']
STRUCTURAL_HALOGENS = set(POLICY['constants']['STRUCTURAL_HALOGENS'])
RDKIT_IMPORT_ERROR = None
tqdm = None
DIMENSIONS = ['Bioaccumulation', 'Toxicity']
OUTPUT_COLUMNS = [d + suffix for d in DIMENSIONS for suffix in ['_score', '_score_basis', '_evidence']]
SCORE_COLUMNS = [d + '_score' for d in DIMENSIONS]
MODEL_FIELDS = [m[k] for m in BCF_MODELS for k in ['logbcf_col', 'adi_col', 'assess_col']] + [m[k] for m in TOXICITY_ENDPOINTS for k in ['pred_col', 'adi_col', 'assess_col'] if m[k]]
NUMERIC_FIELDS = [m[k] for m in BCF_MODELS for k in ['logbcf_col', 'adi_col']] + [m['adi_col'] for m in TOXICITY_ENDPOINTS if m['adi_col']] + [m['pred_col'] for m in TOXICITY_ENDPOINTS if m['kind'] == 'fish_lc50_mgL']

def _is_nullish(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    if not isinstance(v, (dict, list, tuple, set)):
        try:
            return bool(pd.isna(v))
        except (TypeError, ValueError):
            pass
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

def _json_dumps_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_json_default)

def _as_float(v: Any) -> Optional[float]:
    if _is_nullish(v):
        return None
    try:
        return float(v)
    except Exception:
        return None

def _get_compound_key(row: pd.Series, idx: int) -> str:
    return row.get("Inchikey_std") or row.get("InChIKey") or row.get("CAS") or f"row_{idx}"

def _identity_from_row(row: pd.Series) -> dict[str, Any]:
    identity = {}
    for key, columns in {
        "inchikey": ["Inchikey_std", "InChIKey", "Inchikey"],
        "cas": ["CAS"],
        "name": ["Name"],
        "smiles": ["Smile_std", "Smile"],
    }.items():
        for column in columns:
            if column in row and not _is_nullish(row.get(column)):
                identity[key] = row.get(column)
                break
    return identity

def _select_structure_smiles(row: pd.Series) -> Optional[str]:
    """Use standardized SMILES when available, otherwise fall back to reported SMILES."""
    for column in ["Smile_std", "Smile"]:
        if column not in row:
            continue
        value = row.get(column)
        if _is_nullish(value):
            continue
        smiles = str(value).strip()
        if smiles:
            return smiles
    return None

def _pick_curated_db_bioaccumulation(slim: dict) -> Tuple[Optional[float], Optional[str], dict]:
    """Read curated bioaccumulation evidence from `db_extract_info.hazard.B`."""
    hazard = slim.get("hazard") or {}
    b_block = hazard.get("B")
    evidence = {"curated_db": {"selected": None, "all": {}}}

    if not isinstance(b_block, dict) or not b_block:
        return None, None, evidence

    for db, vals in b_block.items():
        if isinstance(vals, list) and vals:
            unique_vals = []
            for x in vals:
                if x not in unique_vals:
                    unique_vals.append(x)
            evidence["curated_db"]["all"][db] = unique_vals[:5]

    db_order = ["PlastChem"] + sorted([d for d in b_block.keys() if d != "PlastChem"])
    for db in db_order:
        vals = b_block.get(db)
        if not (isinstance(vals, list) and vals):
            continue
        for x in vals:
            score = _as_float(x)
            if score is not None:
                evidence["curated_db"]["selected"] = {"db": db, "raw": x, "score": score}
                return score, db, evidence

    return None, None, evidence

def _logbcf_to_bioaccum_score(logbcf):
    for interval in POLICY['bcf_bins']:
        if logbcf >= interval['lower_inclusive']:
            return interval['score']
    return 0.0

def _pick_qsar_bioaccumulation_from_row(
    row: pd.Series,
    adi_threshold: float = 0.5,
) -> Tuple[Optional[float], Optional[str], dict]:
    """Select the first usable BCF model by priority order after strict ADI filtering."""
    evidence = {
        "qsar_bcf_models": {
            "adi_threshold": adi_threshold,
            "priority_order": [m["name"] for m in BCF_MODELS],
            "models": [],
            "selected": None,
            "mapping": "logBCF->Bioaccumulation_score bins: >=3.7=2, >=3.0=1, >=2.0=0.5, <2.0=0",
        }
    }

    for model in BCF_MODELS:
        logbcf = _as_float(row.get(model["logbcf_col"]))
        adi = _as_float(row.get(model["adi_col"]))
        assessment = row.get(model["assess_col"])
        model_record = {
            "model": model["name"],
            "logBCF": logbcf,
            "adi": adi,
            "assessment_raw": None if _is_nullish(assessment) else str(assessment),
            "usable": False,
            "exclude_reason": None,
            "bioaccumulation_score": None,
        }

        if logbcf is None:
            model_record["exclude_reason"] = "missing_logBCF"
            evidence["qsar_bcf_models"]["models"].append(model_record)
            continue
        if adi is None:
            model_record["exclude_reason"] = "missing_ADI"
            evidence["qsar_bcf_models"]["models"].append(model_record)
            continue
        if adi < adi_threshold:
            model_record["exclude_reason"] = f"ADI_below_threshold({adi}<{adi_threshold})"
            evidence["qsar_bcf_models"]["models"].append(model_record)
            continue

        score = _logbcf_to_bioaccum_score(logbcf)
        model_record["usable"] = True
        model_record["bioaccumulation_score"] = score
        evidence["qsar_bcf_models"]["models"].append(model_record)
        evidence["qsar_bcf_models"]["selected"] = {
            "model": model["name"],
            "basis": f"VEGA/IRFMN BCF ({model['name']})",
            "logBCF": logbcf,
            "adi": adi,
            "bioaccumulation_score": score,
        }
        return score, f"QSAR_BCF:{model['name']}", evidence

    return None, None, evidence

def _benzene_ring_atom_indices(mol: Any) -> set[int]:
    """Return atom indices that belong to six-member all-carbon aromatic rings."""
    benzene_atoms: set[int] = set()
    for ring in mol.GetRingInfo().AtomRings():
        if len(ring) != 6:
            continue
        atoms = [mol.GetAtomWithIdx(idx) for idx in ring]
        if all(atom.GetSymbol() == "C" and atom.GetIsAromatic() for atom in atoms):
            benzene_atoms.update(ring)
    return benzene_atoms

def _score_structural_halogen_rule(cl_br_count, benzene_bound_cl_br_count):
    for interval in POLICY['structural_bins']:
        triggers = []
        total, bound = interval['total_cl_br_min'], interval['benzene_bound_cl_br_min']
        if cl_br_count >= total:
            triggers.append(f'cl_br_count>={total}')
        if benzene_bound_cl_br_count >= bound:
            triggers.append(f'benzene_bound_cl_br_count>={bound}')
        if triggers:
            return interval['score'], triggers
    return None, []

def _pick_structural_halogen_bioaccumulation_from_row(row: pd.Series) -> Tuple[Optional[float], Optional[str], dict]:
    """Apply the conservative Cl/Br bioaccumulation structural rule."""
    evidence = {
        "structural_halogen_rule": {
            "selected": None,
            "status": "not_evaluated",
            "smiles": None,
            "cl_br_count": None,
            "benzene_bound_cl_br_count": None,
            "triggered_rules": [],
            "bioaccumulation_score": None,
            "mapping": "Cl/Br>=4 or benzene-bound Cl/Br>=2 => 2; Cl/Br>=2 or benzene-bound Cl/Br>=1 => 1",
        }
    }
    rule = evidence["structural_halogen_rule"]

    smiles = _select_structure_smiles(row)
    rule["smiles"] = smiles
    if smiles is None:
        rule["status"] = "missing_smiles"
        return None, None, evidence

    if RDKIT_IMPORT_ERROR is not None or Chem is None:
        rule["status"] = "rdkit_unavailable"
        rule["error"] = str(RDKIT_IMPORT_ERROR)
        return None, None, evidence

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        rule["status"] = "invalid_smiles"
        return None, None, evidence

    benzene_atoms = _benzene_ring_atom_indices(mol)
    cl_br_count = 0
    benzene_bound_cl_br_count = 0
    for atom in mol.GetAtoms():
        if atom.GetSymbol() not in STRUCTURAL_HALOGENS:
            continue
        cl_br_count += 1
        if any(neighbor.GetIdx() in benzene_atoms for neighbor in atom.GetNeighbors()):
            benzene_bound_cl_br_count += 1

    score, triggers = _score_structural_halogen_rule(cl_br_count, benzene_bound_cl_br_count)
    rule["status"] = "evaluated"
    rule["cl_br_count"] = cl_br_count
    rule["benzene_bound_cl_br_count"] = benzene_bound_cl_br_count
    rule["triggered_rules"] = triggers
    rule["bioaccumulation_score"] = score
    if score is not None:
        rule["selected"] = {
            "basis": STRUCTURAL_HALOGEN_BASIS,
            "bioaccumulation_score": score,
            "triggered_rules": triggers,
        }
        return score, STRUCTURAL_HALOGEN_BASIS, evidence

    return None, None, evidence

def _select_highest_bioaccumulation_score(
    candidates: list[tuple[str, Optional[float], Optional[str]]],
) -> tuple[Optional[float], Optional[str], dict]:
    """Select the highest score, preserving candidate order for ties."""
    candidate_records = [
        {"source": source, "score": score, "basis": basis}
        for source, score, basis in candidates
        if score is not None
    ]
    evidence = {"final_selection": {"candidates": candidate_records, "selected": None, "tied_bases": []}}
    if not candidate_records:
        return None, None, evidence

    max_score = max(record["score"] for record in candidate_records)
    tied_records = [record for record in candidate_records if record["score"] == max_score]
    selected = tied_records[0]
    evidence["final_selection"]["selected"] = selected
    evidence["final_selection"]["tied_bases"] = [record["basis"] for record in tied_records if record["basis"] is not None]
    return selected["score"], selected["basis"], evidence

def build_bioaccumulation_audit_records(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
) -> list[dict[str, Any]]:
    """Build compound-level bioaccumulation evidence records for audit export."""
    records = []
    for idx in range(len(agg_table)):
        row = agg_table.iloc[idx]
        slim = _safe_json_loads(row.get(db_extract_col))
        evidence = _safe_json_loads(row.get("Bioaccumulation_evidence"))
        if not isinstance(slim, dict) and not isinstance(evidence, dict):
            continue
        identity = slim.get("identity") if isinstance(slim, dict) else {}
        identity = identity or _identity_from_row(row)
        hazard = slim.get("hazard") if isinstance(slim, dict) else {}
        hazard = hazard or {}
        b_block = hazard.get("B")
        qsar_block = {}
        for model in BCF_MODELS:
            for col in [model["logbcf_col"], model["adi_col"], model["assess_col"]]:
                if col in agg_table.columns and not _is_nullish(row.get(col)):
                    qsar_block[col] = row.get(col)
        records.append(
            {
                "compound_key": _get_compound_key(row, idx),
                "identity": {k: identity.get(k) for k in ["inchikey", "cas", "name", "smiles"] if k in identity},
                "bioaccumulation_from_db_extract": b_block if isinstance(b_block, dict) else None,
                "bioaccumulation_from_qsar": qsar_block,
                "bioaccumulation_from_structural_halogen_rule": (
                    evidence.get("structural_halogen_rule") if isinstance(evidence, dict) else None
                ),
                "mismatch_report": slim.get("mismatch_report") if isinstance(slim, dict) else [],
            }
        )
    return records

def add_bioaccumulation_columns(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
    out_score_col: str = "Bioaccumulation_score",
    out_basis_col: str = "Bioaccumulation_score_basis",
    out_evidence_col: str = "Bioaccumulation_evidence",
    adi_threshold: float = 0.5,
    show_progress: bool = True,
) -> pd.DataFrame:
    """Add bioaccumulation score, basis, and JSON evidence columns."""
    scores = []
    bases = []
    evidences = []

    iterator = range(len(agg_table))
    if show_progress and tqdm is not None:
        iterator = tqdm(iterator, desc="Computing bioaccumulation scores", unit="compound")

    for i in iterator:
        row = agg_table.iloc[i]
        slim = _safe_json_loads(row.get(db_extract_col))
        evidence: Dict[str, Any] = {}

        db_score, db_basis, ev_db = (None, None, {"curated_db": {"selected": None, "all": {}}})
        if isinstance(slim, dict):
            db_score, db_basis, ev_db = _pick_curated_db_bioaccumulation(slim)
        evidence.update(ev_db)

        qsar_score, qsar_basis, ev_qsar = _pick_qsar_bioaccumulation_from_row(row, adi_threshold=adi_threshold)
        evidence.update(ev_qsar)

        structural_score, structural_basis, ev_structural = _pick_structural_halogen_bioaccumulation_from_row(row)
        evidence.update(ev_structural)

        independent_score, independent_basis, ev_independent = _select_highest_bioaccumulation_score(
            [
                ("qsar_bcf", qsar_score, qsar_basis),
                ("structural_halogen_rule", structural_score, structural_basis),
            ]
        )
        evidence["independent_selection"] = ev_independent["final_selection"]
        final_score, final_basis, final_selection = select_independent_first(
            independent_score=independent_score,
            independent_basis=independent_basis,
            curated_score=db_score,
            curated_basis=(db_basis or "CuratedDB") if db_score is not None else None,
        )
        evidence["final_selection"] = final_selection

        scores.append(final_score)
        bases.append(final_basis)
        evidences.append(_json_dumps_compact(evidence))

    agg_table[out_score_col] = scores
    agg_table[out_basis_col] = bases
    agg_table[out_evidence_col] = evidences
    return agg_table

def _as_binary_activity(v: Any, endpoint_name: Optional[str] = None) -> Optional[int]:
    """Parse generic and endpoint-specific VEGA activity labels into 1/0."""
    if _is_nullish(v):
        return None
    if isinstance(v, (int, float)):
        return 1 if float(v) >= 0.5 else 0
    if isinstance(v, str):
        s = v.strip().lower()
        endpoint_labels = {
            "Ames_mutagenicity_consensus": {
                "mutagenic": 1,
                "non-mutagenic": 0,
            },
            "Carcinogenicity_CAESAR": {
                "carcinogen": 1,
                "non-carcinogen": 0,
            },
            "Carcinogenicity_ISS": {
                "carcinogen": 1,
                "non-carcinogen": 0,
            },
            "DevelopmentalToxicity_CAESAR": {
                "toxicant": 1,
                "non-toxicant": 0,
            },
            "ER_mediated_effect_IRFMN_CERAPP": {
                "active": 1,
                "non-active": 0,
            },
        }
        if endpoint_name in endpoint_labels and s in endpoint_labels[endpoint_name]:
            return endpoint_labels[endpoint_name][s]
        if s in {"1", "true", "t", "yes", "y", "active", "positive", "mutagen", "carcinogen"}:
            return 1
        if s in {"0", "false", "f", "no", "n", "inactive", "negative", "non-mutagen", "non-carcinogen"}:
            return 0
    return None

def _pick_curated_db_toxicity(slim: dict) -> Tuple[Optional[float], Optional[str], dict]:
    """Read curated toxicity evidence from `db_extract_info.hazard.T`."""
    hazard = slim.get("hazard") or {}
    t_block = hazard.get("T")
    evidence = {"curated_db": {"selected": None, "all": {}}}

    if not isinstance(t_block, dict) or not t_block:
        return None, None, evidence

    for db, vals in t_block.items():
        if isinstance(vals, list) and vals:
            unique_vals = []
            for x in vals:
                if x not in unique_vals:
                    unique_vals.append(x)
            evidence["curated_db"]["all"][db] = unique_vals[:8]

    db_order = ["PlastChem"] + sorted([d for d in t_block.keys() if d != "PlastChem"])
    for db in db_order:
        vals = t_block.get(db)
        if not (isinstance(vals, list) and vals):
            continue
        for x in vals:
            score = _as_float(x)
            if score is not None:
                evidence["curated_db"]["selected"] = {"db": db, "raw": x, "score": score}
                return score, db, evidence

    return None, None, evidence

def _fish_lc50_to_score_mg_l(lc50_mg_l):
    for interval in POLICY['fish_bins']:
        if lc50_mg_l <= interval['upper_inclusive']:
            return interval['score']
    return 0.0

def _activity_endpoint_to_score(active01: int, severity: Optional[str]) -> float:
    if active01 == 0:
        return 0.0
    if severity == "high":
        return 2.0
    return 1.0

def _pick_qsar_toxicity_from_row(
    row: pd.Series,
    adi_threshold: float = 0.5,
) -> Tuple[Optional[float], Optional[str], dict]:
    """Compute QSAR toxicity score using the conservative maximum usable endpoint."""
    evidence = {
        "qsar_toxicity": {
            "adi_threshold": adi_threshold,
            "endpoints": [],
            "selected": None,
            "combine_rule": "max_endpoint_score",
        }
    }
    best_score = None
    best_basis = None
    best_detail = None

    for endpoint in TOXICITY_ENDPOINTS:
        pred_raw = row.get(endpoint["pred_col"])
        pred_float = _as_float(pred_raw)
        adi = _as_float(row.get(endpoint["adi_col"])) if endpoint["adi_col"] else None
        assessment = row.get(endpoint["assess_col"])
        endpoint_record = {
            "endpoint": endpoint["name"],
            "pred_col": endpoint["pred_col"],
            "pred_raw": None if _is_nullish(pred_raw) else pred_raw,
            "adi_col": endpoint["adi_col"],
            "adi": adi,
            "assessment_raw": None if _is_nullish(assessment) else str(assessment),
            "usable": False,
            "exclude_reason": None,
            "endpoint_score": None,
        }

        if _is_nullish(pred_raw):
            endpoint_record["exclude_reason"] = "missing_prediction"
            evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)
            continue

        if endpoint["adi_col"]:
            if adi is None:
                endpoint_record["exclude_reason"] = "missing_ADI"
                evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)
                continue
            if adi < adi_threshold:
                endpoint_record["exclude_reason"] = f"ADI_below_threshold({adi}<{adi_threshold})"
                evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)
                continue

        if endpoint["kind"] == "binary":
            activity = _as_binary_activity(pred_raw, endpoint_name=endpoint["name"])
            if activity is None:
                endpoint_record["exclude_reason"] = "unparsable_binary_activity"
                evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)
                continue
            score = _activity_endpoint_to_score(activity, endpoint["severity"])
        elif endpoint["kind"] == "fish_lc50_mgL":
            if pred_float is None:
                endpoint_record["exclude_reason"] = "unparsable_numeric"
                evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)
                continue
            score = _fish_lc50_to_score_mg_l(pred_float)
        else:
            endpoint_record["exclude_reason"] = "unknown_endpoint_kind"
            evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)
            continue

        endpoint_record["usable"] = True
        endpoint_record["endpoint_score"] = score
        evidence["qsar_toxicity"]["endpoints"].append(endpoint_record)

        if best_score is None or score > best_score:
            best_score = score
            best_basis = f"QSAR_Toxicity:{endpoint['name']}"
            best_detail = {
                "endpoint": endpoint["name"],
                "score": score,
                "pred_raw": endpoint_record["pred_raw"],
                "adi": adi,
                "assessment_raw": endpoint_record["assessment_raw"],
            }

    if best_score is not None:
        evidence["qsar_toxicity"]["selected"] = best_detail
        return best_score, best_basis, evidence

    return None, None, evidence

def build_toxicity_audit_records(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
) -> list[dict[str, Any]]:
    """Build compound-level toxicity evidence records for audit export."""
    records = []
    for idx in range(len(agg_table)):
        row = agg_table.iloc[idx]
        slim = _safe_json_loads(row.get(db_extract_col))
        if not isinstance(slim, dict):
            continue
        identity = slim.get("identity") or {}
        hazard = slim.get("hazard") or {}
        t_block = hazard.get("T")
        label_block = hazard.get("toxicological_labels")
        qsar_block = {}
        for endpoint in TOXICITY_ENDPOINTS:
            for col in [endpoint["pred_col"], endpoint["adi_col"], endpoint["assess_col"]]:
                if col and col in agg_table.columns and not _is_nullish(row.get(col)):
                    qsar_block[col] = row.get(col)
        records.append(
            {
                "compound_key": _get_compound_key(row, idx),
                "identity": {k: identity.get(k) for k in ["inchikey", "cas", "name", "smiles"] if k in identity},
                "toxicity_from_db_extract": t_block if isinstance(t_block, dict) else None,
                "toxicological_labels": label_block if isinstance(label_block, dict) else None,
                "toxicity_from_qsar": qsar_block,
                "mismatch_report": slim.get("mismatch_report") or [],
            }
        )
    return records

def add_toxicity_columns(
    agg_table: pd.DataFrame,
    db_extract_col: str = "db_extract_info",
    out_score_col: str = "Toxicity_score",
    out_basis_col: str = "Toxicity_score_basis",
    out_evidence_col: str = "Toxicity_evidence",
    adi_threshold: float = 0.5,
    show_progress: bool = True,
) -> pd.DataFrame:
    """Add toxicity score, basis, and JSON evidence columns."""
    scores: List[Optional[float]] = []
    bases: List[Optional[str]] = []
    evidences: List[str] = []

    iterator = range(len(agg_table))
    if show_progress and tqdm is not None:
        iterator = tqdm(iterator, desc="Computing toxicity scores", unit="compound")

    for i in iterator:
        row = agg_table.iloc[i]
        slim = _safe_json_loads(row.get(db_extract_col))
        evidence: Dict[str, Any] = {}

        db_score, db_basis, ev_db = (None, None, {"curated_db": {"selected": None, "all": {}}})
        if isinstance(slim, dict):
            db_score, db_basis, ev_db = _pick_curated_db_toxicity(slim)
        evidence.update(ev_db)

        qsar_score, qsar_basis, ev_qsar = _pick_qsar_toxicity_from_row(row, adi_threshold=adi_threshold)
        evidence.update(ev_qsar)

        final_score, final_basis, final_selection = select_independent_first(
            independent_score=qsar_score,
            independent_basis=qsar_basis,
            curated_score=db_score,
            curated_basis=(db_basis or "CuratedDB") if db_score is not None else None,
        )
        evidence["final_selection"] = final_selection

        scores.append(final_score)
        bases.append(final_basis)
        evidences.append(_json_dumps_compact(evidence))

    agg_table[out_score_col] = scores
    agg_table[out_basis_col] = bases
    agg_table[out_evidence_col] = evidences
    return agg_table


def scoring_inputs(compounds, *, historical=False):
    """Project B/T fields and enforce identity availability before all endpoints."""
    required = ['inchikey', 'qsar_smiles', 'db_extract_info', *MODEL_FIELDS]
    if not historical:
        required += ['qsar_identity_status', 'qsar_identity_reason', 'qsar_evidence_available']
    missing = set(required) - set(compounds.columns)
    if missing:
        raise ValueError('Missing B/T input columns: ' + ', '.join(sorted(missing)))
    if compounds['inchikey'].duplicated().any() or compounds['inchikey'].map(lambda v: not isinstance(v, str) or not v.strip()).any():
        raise ValueError('B/T inputs require unique nonempty chemical keys.')
    frame = compounds[['inchikey', 'qsar_smiles', 'db_extract_info', *MODEL_FIELDS]].copy()
    frame['Inchikey_std'] = frame['inchikey']
    frame['Smile_std'] = frame['qsar_smiles']
    if not historical:
        review = compounds['qsar_identity_status'].eq('review_required')
        flags = compounds['qsar_evidence_available'].astype(str)
        if not flags.isin(['True', 'False']).all():
            raise ValueError('B/T availability flags must be explicit booleans.')
        if frame.loc[review, MODEL_FIELDS].map(lambda v: not _is_nullish(v)).any().any() or flags.loc[review].ne('False').any():
            raise ValueError('Identity-review prediction leaked into B/T analysis.')
        frame.loc[flags.eq('False'), MODEL_FIELDS] = None
    for column in NUMERIC_FIELDS:
        frame[column] = frame[column].map(_as_float)
        if frame[column].dropna().map(lambda v: not math.isfinite(v)).any():
            raise ValueError('Nonfinite numerical B/T input: ' + column)
    payloads = []
    for text in frame['db_extract_info']:
        payload = json.loads(text)
        if not isinstance(payload, dict) or not isinstance(payload.get('hazard', {}), dict):
            raise ValueError('B/T evidence must contain a valid hazard object.')
        payloads.append(_json({**{k: payload[k] for k in ['identity', 'mismatch_report'] if k in payload},
                              'hazard': {k: v for k, v in payload.get('hazard', {}).items() if k in ['B', 'T', 'toxicological_labels']}}))
    frame['db_extract_info'] = payloads
    return frame


def score_bt(compounds, *, historical=False):
    """Evaluate independent B and T dimensions; no aggregate score is created."""
    frame = scoring_inputs(compounds, historical=historical)
    with rdBase.BlockLogs():
        frame = add_bioaccumulation_columns(frame, adi_threshold=POLICY['adi_threshold'], show_progress=False)
    frame = add_toxicity_columns(frame, adi_threshold=POLICY['adi_threshold'], show_progress=False)
    audits = {'bioaccumulation': build_bioaccumulation_audit_records(frame),
              'toxicity': build_toxicity_audit_records(frame)}
    result = frame[['inchikey', *OUTPUT_COLUMNS]].copy()
    if not historical:
        for i, row in compounds.reset_index(drop=True).iterrows():
            if row['qsar_identity_status'] != 'review_required':
                continue
            context = {'status': 'review_required', 'reason': row['qsar_identity_reason'],
                       'prediction_exclusion_reason': 'identity_review_required',
                       'independent_structure_and_curated_evidence': 'remain_eligible'}
            for dimension, block, entries in [('Bioaccumulation', 'qsar_bcf_models', 'models'), ('Toxicity', 'qsar_toxicity', 'endpoints')]:
                column = dimension + '_evidence'
                payload = json.loads(result.iloc[i][column])
                for candidate in payload[block][entries]:
                    candidate['exclude_reason'] = 'identity_review_required'
                payload['identity_review'] = context
                result.at[result.index[i], column] = _json(payload)
                audits[dimension.lower()][i]['identity_review'] = context
    return result, audits


def _historical_inputs(compounds, qsar):
    """Restore only model values from the verified Stage 3 historical report."""
    if qsar['inchikey'].duplicated().any() or set(qsar['inchikey']) != set(compounds['inchikey']):
        raise ValueError('Historical B/T identity sets differ from analysis inputs.')
    aligned = qsar.set_index('inchikey').loc[compounds['inchikey']]
    if aligned['qsar_smiles'].tolist() != compounds['qsar_smiles'].tolist():
        raise ValueError('B/T structural representation differs from Stage 3 local screening.')
    result = compounds.copy()
    for column in MODEL_FIELDS:
        result[column] = aligned[column].to_numpy()
    return result


def _read_jsonl(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def _pathway_decisions(dimension, evidence):
    """Explain candidate selection without changing the historical evidence payload."""
    rows = []
    if dimension == 'Bioaccumulation':
        block = evidence['qsar_bcf_models']
        evaluated = {r['model']: r for r in block['models']}
        for model in BCF_MODELS:
            record = evaluated.get(model['name'])
            reason = 'not_evaluated_after_higher_priority_usable_model' if record is None else 'selected_by_model_priority' if record['usable'] else record['exclude_reason']
            rows.append({'candidate': model['name'], 'reason': reason})
        selected = evidence['independent_selection']['selected']
        for candidate in evidence['independent_selection']['candidates']:
            reason = 'selected_independent_pathway' if candidate == selected else 'same_score_later_pathway' if candidate['score'] == selected['score'] else 'lower_independent_score'
            rows.append({'candidate': candidate['source'], 'reason': reason})
        structural = evidence['structural_halogen_rule']
        if structural['bioaccumulation_score'] is None:
            rows.append({'candidate': 'structural_halogen_rule', 'reason': 'no_structural_trigger' if structural['status'] == 'evaluated' else structural['status']})
    else:
        block = evidence['qsar_toxicity']
        selected = block['selected']
        for record in block['endpoints']:
            reason = record['exclude_reason'] if not record['usable'] else 'selected_maximum_endpoint' if record['endpoint'] == selected['endpoint'] else 'same_score_later_endpoint' if record['endpoint_score'] == selected['score'] else 'lower_endpoint_score'
            rows.append({'candidate': record['endpoint'], 'reason': reason})
    selection = evidence['final_selection']
    reason = 'selected_curated_fallback' if selection['selected']['source_class'] == 'curated_fallback' else 'independent_evidence_takes_precedence' if selection['curated_candidate']['score'] is not None else 'no_usable_curated_evidence'
    rows.append({'candidate': 'curated', 'reason': reason})
    return rows


def _change_reason(dimension, before, after, evidence):
    """Describe the permitted prediction-isolation effect without equating missing to zero."""
    selected = evidence['final_selection']['selected']
    if selected['source_class'] == 'curated_fallback':
        return 'identity_review_predictions_excluded_curated_fallback'
    if selected['source_class'] == 'independent_computation':
        return 'identity_review_predictions_excluded_independent_structure_retained'
    if _is_nullish(before):
        return 'identity_review_predictions_excluded_remains_unavailable'
    return 'identity_review_predictions_excluded_no_independent_or_curated_fallback'


@dataclass
class BTHazardResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    impacts: pd.DataFrame
    summary: pd.DataFrame
    structures: pd.DataFrame
    audits: dict
    manifest: dict

    def write_reports(self, output_dir):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in [('compound_pbmt_hazard', self.compounds), ('bt_historical', self.historical),
                            ('identity_review_bt_impacts', self.impacts), ('bt_summary', self.summary),
                            ('bt_structure_mapping', self.structures)]:
            path = folder / (name + '.csv')
            frame.to_csv(path, index=False, encoding='utf-8', lineterminator='\n')
            outputs[path.name] = _file_hash(path)
        for name, rows in self.audits.items():
            path = folder / (name + '.jsonl')
            with path.open('w', encoding='utf-8', newline='\n') as stream:
                for row in rows:
                    stream.write(_json(row) + '\n')
            outputs[path.name] = _file_hash(path)
        (folder / 'bt_manifest.json').write_text(json.dumps({**self.manifest, 'output_sha256': outputs}, indent=2) + '\n', encoding='utf-8')


def integrate_bt_hazard(pm_results):
    """Extend the verified Stage 5A analysis while retaining all prior columns."""
    pm = Path(pm_results)
    root = pm.parent
    paths = {'pm': pm / 'hazard_manifest.json', 'qsar': root / 'stage3' / 'qsar_manifest.json',
             'basic': root / 'stage4' / 'evidence_manifest.json'}
    hashes = {name: _file_hash(path) for name, path in paths.items()}
    manifests = {name: json.loads(path.read_text(encoding='utf-8')) for name, path in paths.items()}
    if POLICY['schema_version'] != 1 or _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError('B/T policy changed; restart the process.')
    for name, path in paths.items():
        _verify_outputs(path.parent, manifests[name])
    for name in ['qsar', 'basic']:
        if manifests['pm']['upstream_manifests_sha256'][name] != hashes[name]:
            raise ValueError('B/T inputs refer to different upstream runs.')
    if (_file_hash(Path(__file__).with_name('hazard.py')) != manifests['pm']['implementation_sha256'] or
        PM_POLICY_HASH != manifests['pm']['policy_sha256'] or
        _file_hash(Path(__file__).with_name('hazard_policy.json')) != PM_POLICY_HASH):
        raise ValueError('The shared source-selection implementation or policy differs from Stage 5A.')
    if _file_hash(Path(__file__).with_name('qsar_models.json')) != manifests['pm']['qsar_model_mapping_sha256']:
        raise ValueError('B/T model definitions differ from Stage 5A.')
    compounds = _read_csv(pm / 'compound_pm_hazard.csv')
    if not compounds['pm_result_role'].eq('analysis_after_identity_isolation').all():
        raise ValueError('B/T requires the Stage 5A analysis table, not historical results.')
    require_prediction_isolation(compounds)
    historical_inputs = _historical_inputs(compounds, _read_csv(root / 'stage3' / 'compound_qsar.csv'))
    historical, historic_audits = score_bt(historical_inputs, historical=True)
    analysis, analysis_audits = score_bt(compounds)
    result = compounds.copy()
    for column in OUTPUT_COLUMNS:
        result[column] = analysis[column].to_numpy()
    for dimension in DIMENSIONS:
        usable = result[dimension + '_score'].notna()
        result[dimension.lower() + '_available'] = usable
        result[dimension.lower() + '_unavailable_reason'] = [
            '' if ok else 'identity_review_required_no_independent_or_curated_fallback' if status == 'review_required' else 'no_usable_evidence'
            for ok, status in zip(usable, result['qsar_identity_status'])]
    result['bt_result_role'] = 'analysis_after_identity_isolation'
    historical['result_role'] = 'historical_reproduction_only'
    require_prediction_isolation(result)
    audits = {**{name + '_historical_audit': rows for name, rows in historic_audits.items()},
              **{name + '_analysis_audit': rows for name, rows in analysis_audits.items()}}
    audits['bt_curated_source_links'] = [row for row in _read_jsonl(root / 'stage4' / 'basic_evidence_audit.jsonl') if row.get('field_path') in ['hazard.B', 'hazard.T']]
    audits['identity_review_source_links'] = _read_jsonl(pm / 'identity_review_source_links.jsonl')
    structures, decisions, impacts = [], [], []
    for i, row in result.iterrows():
        structure = json.loads(row['Bioaccumulation_evidence'])['structural_halogen_rule']
        structures.append({'inchikey': row['inchikey'], 'representative_record_id': row['representative_record_id'],
                           'source_smiles_standard': row['smiles_standard'], 'scoring_smiles': row['qsar_smiles'],
                           'text_changed_by_local_screening': row['smiles_standard'] != row['qsar_smiles'],
                           'mapping': 'Stage 2 smiles_standard -> Stage 3 local screening qsar_smiles -> structural rule',
                           'model_report_structure_used': False, 'qsar_manifest_sha256': hashes['qsar'],
                           'structural_status': structure['status'], 'cl_br_count': structure['cl_br_count'],
                           'benzene_bound_cl_br_count': structure['benzene_bound_cl_br_count'],
                           'triggered_rules_json': _json(structure['triggered_rules']),
                           'structural_score': structure['bioaccumulation_score'], 'rdkit_version': rdBase.rdkitVersion})
        for dimension in DIMENSIONS:
            payload = json.loads(row[dimension + '_evidence'])
            decision = {'compound_key': row['inchikey'], 'dimension': dimension,
                        'vega_row_no': row['vega_row_no'], 'qsar_inchikey': row['qsar_inchikey'],
                        'identity_status': row['qsar_identity_status'], 'identity_reason': row['qsar_identity_reason'],
                        'source_selection': payload['final_selection'], 'pathway_decisions': _pathway_decisions(dimension, payload),
                        'upstream_manifests_sha256': hashes,
                        'available': bool(pd.notna(row[dimension + '_score'])),
                        'unavailable_reason': row[dimension.lower() + '_unavailable_reason']}
            decisions.append(decision)
            if row['qsar_identity_status'] == 'review_required':
                reason = _change_reason(dimension, historical.at[i, dimension + '_score'], row[dimension + '_score'], payload)
                for suffix in ['_score', '_score_basis', '_evidence']:
                    column = dimension + suffix
                    before, after = historical.at[i, column], row[column]
                    impacts.append({'inchikey': row['inchikey'], 'field': column,
                                    'historical_value': before, 'analysis_value': after,
                                    'changed': (None if _is_nullish(before) else before) != (None if _is_nullish(after) else after),
                                    'identity_reason': row['qsar_identity_reason'], 'change_reason': reason,
                                    'historical_basis': historical.at[i, dimension + '_score_basis'],
                                    'analysis_basis': row[dimension + '_score_basis'], 'vega_row_no': row['vega_row_no']})
    audits['bt_decisions'] = decisions
    summary = []
    for view, frame in [('historical', historical), ('analysis', result)]:
        for column in SCORE_COLUMNS:
            summary.append({'view': view, 'field': column, 'compounds': len(frame),
                            'available': int(frame[column].notna().sum()), 'unavailable': int(frame[column].isna().sum()),
                            'zero_scores': int(frame[column].eq(0).sum())})
    for name, path in paths.items():
        if _file_hash(path) != hashes[name]:
            raise ValueError('Upstream B/T manifest changed during scoring.')
        _verify_outputs(path.parent, manifests[name])
    if _file_hash(DEFAULT_POLICY) != POLICY_HASH:
        raise ValueError('B/T policy changed during scoring.')
    counts = {'compounds': len(result), 'identity_review_compounds': int(result['qsar_identity_status'].eq('review_required').sum()),
              'identity_review_source_links': len(audits['identity_review_source_links']), 'curated_source_links': len(audits['bt_curated_source_links']),
              'structure_text_changes': sum(r['text_changed_by_local_screening'] for r in structures),
              'gic_name_review_required': int(result['gic_name_review_required'].eq('True').sum()),
              'gic_tag_expansion_review_required': int(result['gic_shared_identifier_tag_expansion'].eq('True').sum()),
              'bioaccumulation_available': int(result['bioaccumulation_available'].sum()), 'toxicity_available': int(result['toxicity_available'].sum())}
    manifest = {'schema_version': 1, 'scope': POLICY['scope'], 'policy_sha256': POLICY_HASH,
                'implementation_sha256': _file_hash(Path(__file__)),
                'shared_pm_implementation_sha256': _file_hash(Path(__file__).with_name('hazard.py')),
                'qsar_model_mapping_sha256': _file_hash(Path(__file__).with_name('qsar_models.json')),
                'upstream_manifests_sha256': hashes, 'counts': counts, 'rules': POLICY['rules'],
                'scoring_input_columns': MODEL_FIELDS + ['qsar_smiles'], 'scoring_evidence_paths': ['hazard.B', 'hazard.T'],
                'audit_only_evidence_paths': ['hazard.toxicological_labels'], 'historical_sources': POLICY['historical_sources'],
                'runtime': {'python': platform.python_version(), 'pandas': pd.__version__, 'rdkit': rdBase.rdkitVersion}}
    return BTHazardResult(result, historical, pd.DataFrame(impacts), pd.DataFrame(summary), pd.DataFrame(structures), audits, manifest)
