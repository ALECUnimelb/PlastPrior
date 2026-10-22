"""Screen compounds and integrate a fingerprinted VEGA batch with identity audits.

Values assigned through a frozen row manifest reproduce historical associations.
An association whose report structure disagrees remains unverified, even when
the numerical prediction agrees with the historical result.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import platform

import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, inchi, rdMolDescriptors

from .identity import IdentityResult, REQUIRED_RDKIT, _frame_hash
from .inputs import _file_hash, resolve_data_root


DEFAULT_MODELS = Path(__file__).with_name("qsar_models.json")
MISSING_TOKENS = {"", "-", "na", "n/a", "nan", "none", "null", "missing", "unknown"}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _csv_hash(frame: pd.DataFrame, *, header=True) -> str:
    return hashlib.sha256(frame.to_csv(index=False, header=header, lineterminator="\n").encode("utf-8")).hexdigest()


def _screen(compounds: pd.DataFrame, policy: dict) -> pd.DataFrame:
    """Retain Stage 2 structures and store the historical QC representation separately."""
    if compounds.empty or compounds["inchikey"].duplicated().any():
        raise ValueError("QSAR screening requires a non-empty, unique full-key inventory.")
    rows = []
    with rdBase.BlockLogs():
        for row in compounds.sort_values("inchikey").to_dict("records"):
            smiles = row["smiles_standard"]
            flags, reasons = [], []
            qc = {"inchikey": row["inchikey"], "qsar_inchikey": row["qsar_inchikey"],
                  "representative_record_id": row["representative_record_id"],
                  "qsar_smiles": smiles, "molecular_weight": None, "keep_for_vega": True}
            if not smiles:
                flags.append("missing_smiles")
                reasons.append("Missing SMILES")
            else:
                if "." in smiles:
                    flags.append("multi_component")
                    reasons.append("Multi-component structure (contains '.')")
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    flags.append("invalid_smiles")
                    reasons.append("Invalid SMILES (RDKit parse failed)")
                else:
                    qc["qsar_smiles"] = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
                    mw = Descriptors.MolWt(mol)
                    qc["molecular_weight"] = mw
                    if not policy["mw_min"] <= mw <= policy["mw_max"]:
                        flags.append("mw_out_of_range")
                        reasons.append(f"Molecular weight out of QSAR range (MW={mw:.1f})")
                    atoms = {atom.GetSymbol() for atom in mol.GetAtoms()}
                    if "C" not in atoms:
                        flags.append("non_organic")
                        reasons.append("Non-organic structure (no carbon atom)")
                    if atoms & set(policy["metals"]):
                        flags.append("contains_metal")
                        reasons.append("Contains metal atom")
                    # Preserve the historical lexical warning; this is not a net-charge test.
                    if "+" in smiles or "-" in smiles:
                        flags.append("charged_structure")
                    if sum(a.GetSymbol() in {"F", "Cl", "Br", "I"} for a in mol.GetAtoms()) >= policy["heavy_halogen_threshold"]:
                        flags.append("heavy_halogenated")
            excluded = {"missing_smiles", "invalid_smiles", "multi_component", "non_organic", "contains_metal", "mw_out_of_range"}
            qc.update(keep_for_vega=not bool(set(flags) & excluded), qc_flags=";".join(flags),
                      exclusion_reason="; ".join(reasons))
            rows.append(qc)
    return pd.DataFrame(rows)


def _input_manifest(screening: pd.DataFrame) -> pd.DataFrame:
    eligible = screening.loc[screening["keep_for_vega"]].copy()
    if eligible["qsar_inchikey"].eq("").any() or eligible["qsar_smiles"].eq("").any():
        raise ValueError("Eligible structures must have a QSAR key and SMILES.")
    selected = eligible.drop_duplicates("qsar_inchikey", keep="first").reset_index(drop=True)
    # Preserve the frozen batch's external manifest schema and first-key order.
    result = selected[["qsar_inchikey", "inchikey", "qsar_smiles"]].rename(columns={
        "qsar_inchikey": "Qsar_inchikey", "inchikey": "Inchikey_std", "qsar_smiles": "Smile_std"})
    result.insert(0, "vega_row_no", range(1, len(result) + 1))
    return result


def _load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or not config.get("policy_version") or not config.get("models"):
        raise ValueError("A versioned QSAR model declaration is required.")
    for field in ("id", "filename", "name"):
        values = [m[field] for m in config["models"]]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate model {field} declarations.")
    for model in config["models"]:
        if any(c in model["filename"] for c in ("/", "\\")):
            raise ValueError("Model filenames must be basenames.")
        fields = [p["column"] for p in model["predictions"]] + model["quality_columns"]
        if set(fields) - set(model["headers"]):
            raise ValueError(f"Undeclared prediction or quality column: {model['id']}")
        if len(model["headers"]) != len(set(model["headers"])):
            raise ValueError(f"Duplicate report header labels: {model['id']}")
        if set(model["merge_columns"]) - set(fields) or set(model["numeric_columns"]) - set(model["merge_columns"]):
            raise ValueError(f"Invalid merge projection: {model['id']}")
    return config


def _read_report(path: Path, model: dict) -> tuple[pd.DataFrame, list[dict], dict]:
    """Parse a frozen tab-separated report without silently skipping any row.

    Left-aligned padding and extra columns before Remarks reproduce the historical
    layout. Every nonstandard row retains its complete raw cells for review.
    """
    digest = _file_hash(path)
    if digest != model["sha256"]:
        raise ValueError(f"Report differs from the declared frozen version: {path.name}")
    lines = path.read_text(encoding=model["encoding"]).splitlines()
    if len(lines) < 3 or lines[1].strip() != model["model_metadata"] or lines[2].strip() != model["calculation_metadata"]:
        raise ValueError(f"Model version metadata differs: {path.name}")
    header_index = next((i for i, line in enumerate(lines[:1000])
                         if line.strip().startswith("No.") and "SMILES" in line), None)
    if header_index is None:
        raise ValueError(f"Missing VEGA tabular header: {path.name}")
    header = [" ".join(c.split()) for c in lines[header_index].split("\t")]
    if header != model["headers"] or not {"No.", "SMILES", "Assessment"} <= set(header):
        raise ValueError(f"Report header differs from the explicit mapping: {path.name}")
    body = [(i + 1, line.split("\t")) for i, line in enumerate(lines) if i > header_index and line.strip()]
    if not body:
        raise ValueError(f"No prediction rows: {path.name}")
    widths = Counter(len(row) for _, row in body)
    if set(widths) - set(model["allowed_row_widths"]):
        raise ValueError(f"Unexpected report row width: {path.name}")
    max_width = max(len(header), max(widths))
    extra = max_width - len(header)
    if extra and header[-1] != "Remarks":
        raise ValueError("Extra report cells require an explicitly recognised trailing Remarks field.")
    columns = (header[:-1] + [f"Extra AD column {i}" for i in range(1, extra + 1)] + ["Remarks"]
               if extra else header)
    rows, audit = [], []
    for physical_line, values in body:
        padded = values + [""] * (max_width - len(values))
        rows.append(padded)
        if len(values) != len(header) or (extra and len(values) != max_width):
            audit.append({"model_id": model["id"], "source_file": path.name, "source_sha256": digest,
                          "source_line_number": physical_line, "vega_row_no": values[0],
                          "declared_columns": len(header), "observed_columns": len(values),
                          "layout_action": "extra_cells_before_remarks" if len(values) > len(header)
                                           else "legacy_left_aligned_padding",
                          "raw_cells_json": _json(values)})
    frame = pd.DataFrame(rows, columns=columns)
    frame["source_line_number"] = [line for line, _ in body]
    if _file_hash(path) != digest:
        raise ValueError(f"Report changed during parsing: {path.name}")
    return frame, audit, {"header_line_number": header_index + 1, "row_width_counts_json": _json(dict(sorted(widths.items())))}


@lru_cache(maxsize=50_000)
def _structure_details(smiles: str) -> dict:
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raw = Chem.MolFromSmiles(smiles, sanitize=False)
            problems = ([{"type": p.GetType(), "message": p.Message()} for p in Chem.DetectChemistryProblems(raw)]
                        if raw is not None else [{"type": "SmilesParseFailure", "message": "SMILES syntax could not be parsed."}])
            return {"inchikey": "", "formula": "", "radical_electrons": None, "formal_charge": None,
                    "canonical_smiles": "", "parse_problems_json": _json(problems)}
        key = inchi.MolToInchiKey(mol)
        return {"inchikey": key, "formula": rdMolDescriptors.CalcMolFormula(mol),
                "radical_electrons": sum(a.GetNumRadicalElectrons() for a in mol.GetAtoms()),
                "formal_charge": Chem.GetFormalCharge(mol),
                "canonical_smiles": Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
                "parse_problems_json": "[]"}


def _identity_audit(manifest: pd.DataFrame, report_smiles: list[str], expected_review_rows: list[int]) -> pd.DataFrame:
    rows = []
    for row, reported in zip(manifest.to_dict("records"), report_smiles):
        incoming = _structure_details(row["Smile_std"])
        observed = _structure_details(reported)
        if incoming["inchikey"] != row["Qsar_inchikey"]:
            raise ValueError(f"QSAR input key disagrees with its own structure at row {row['vega_row_no']}.")
        verified = observed["inchikey"] == row["Qsar_inchikey"]
        reason, evidence = "exact_key_match", "Report-derived full key matches the frozen input key."
        if not verified:
            if observed["parse_problems_json"] != "[]":
                reason = ("report_aromaticity_kekulization_failure" if "KekulizeException" in observed["parse_problems_json"]
                          else "report_structure_parse_failure")
                evidence = "The reported representation cannot be sanitised by the pinned RDKit version."
            elif not observed["inchikey"]:
                reason, evidence = "report_key_generation_failure", "The report molecule produced no InChIKey."
            elif incoming["formula"] != observed["formula"] and incoming["radical_electrons"] != observed["radical_electrons"]:
                reason = "formula_and_radical_representation_difference"
                evidence = "Input and report representations differ in molecular formula and radical electron count under RDKit."
            else:
                reason, evidence = "full_key_difference", "Input and report structures yield different full keys."
        rows.append({"vega_row_no": row["vega_row_no"], "qsar_inchikey": row["Qsar_inchikey"],
                     "input_representative_inchikey": row["Inchikey_std"], "input_smiles": row["Smile_std"],
                     "report_smiles": reported, "report_inchikey": observed["inchikey"],
                     "identity_verified": verified, "identity_status": "exact_key_match" if verified else "review_required",
                     "reason": reason, "diagnostic_evidence": evidence,
                     "cause_assessment": "Not applicable" if verified else
                         "Observed representation discrepancy; the responsible processing/export step and chemical correctness remain unconfirmed.",
                     **{"input_" + k: v for k, v in incoming.items() if k not in {"inchikey", "canonical_smiles"}},
                     **{"report_" + k: v for k, v in observed.items() if k not in {"inchikey", "canonical_smiles"}},
                     "association_method": "frozen_input_row_manifest",
                     "review_disposition": "Not required" if verified else "Pending scientific review; historical association only"})
    audit = pd.DataFrame(rows)
    for field in ("input_radical_electrons", "report_radical_electrons", "input_formal_charge", "report_formal_charge"):
        audit[field] = audit[field].astype("Int64")
    actual = audit.loc[~audit["identity_verified"], "vega_row_no"].tolist()
    if actual != sorted(expected_review_rows):
        raise ValueError(f"Identity exceptions differ from the frozen batch declaration: {actual}")
    return audit


def _numeric_projection(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    numeric = pd.to_numeric(raw, errors="coerce")
    missing = raw.str.strip().str.lower().isin(MISSING_TOKENS)
    status = pd.Series("numeric", index=raw.index)
    status.loc[numeric.isna() & missing] = "source_missing_token"
    status.loc[numeric.isna() & ~missing] = "unparseable_numeric_token"
    return numeric, status


@dataclass
class QSARResult:
    screening: pd.DataFrame
    input_manifest: pd.DataFrame
    predictions: pd.DataFrame
    compounds: pd.DataFrame
    identity_audit: pd.DataFrame
    anomaly_sources: pd.DataFrame
    anomaly_reports: pd.DataFrame
    model_summary: pd.DataFrame
    layout_audit: pd.DataFrame
    numeric_audit: pd.DataFrame
    missing_value_audit: pd.DataFrame
    manifest: dict

    def write_reports(self, output_dir: str | Path) -> None:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in (("qsar_screening", self.screening), ("vega_input_row_manifest", self.input_manifest),
                            ("qsar_predictions", self.predictions), ("compound_qsar", self.compounds),
                            ("qsar_identity_audit", self.identity_audit), ("identity_anomaly_sources", self.anomaly_sources),
                            ("identity_anomalies", self.identity_audit.loc[~self.identity_audit["identity_verified"]]),
                            ("identity_anomaly_reports", self.anomaly_reports), ("qsar_model_summary", self.model_summary),
                            ("report_layout_audit", self.layout_audit), ("numeric_conversion_audit", self.numeric_audit)):
            path = folder / (name + ".csv")
            frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            outputs[path.name] = _file_hash(path)
        path = folder / "missing_value_audit.csv"
        self.missing_value_audit.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        outputs[path.name] = _file_hash(path)
        path = folder / "vega_input_smiles.txt"
        self.input_manifest[["Smile_std"]].to_csv(path, index=False, header=False, encoding="utf-8", lineterminator="\n")
        outputs[path.name] = _file_hash(path)
        (folder / "qsar_manifest.json").write_text(json.dumps({**self.manifest, "output_sha256": outputs},
            indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def integrate_qsar(identities: IdentityResult, data_root: str | Path = "data", *,
                   models_path: str | Path = DEFAULT_MODELS) -> QSARResult:
    """Integrate the declared frozen reports; retain all unverified associations as such."""
    if version("rdkit") != REQUIRED_RDKIT:
        raise RuntimeError(f"QSAR integration requires RDKit {REQUIRED_RDKIT}.")
    models_path = Path(models_path)
    config_hash = _file_hash(models_path)
    config = _load_config(models_path)
    folder = resolve_data_root(data_root) / "Vega output"
    if {p.name for p in folder.glob("report_*.txt")} != {m["filename"] for m in config["models"]}:
        raise ValueError("The frozen batch has missing or undeclared VEGA report files.")
    screening = _screen(identities.compounds, config["screening"])
    manifest = _input_manifest(screening)
    batch = config["frozen_batch"]
    if (_csv_hash(manifest) != batch["input_manifest_sha256"] or
            _csv_hash(manifest[["Smile_std"]], header=False) != batch["input_smiles_sha256"]):
        raise ValueError("Generated input batch differs from the frozen VEGA batch; reports cannot be assigned by row.")
    predictions = pd.DataFrame({"qsar_inchikey": manifest["Qsar_inchikey"],
                                "Basic | Inchikey14": manifest["Qsar_inchikey"].str.split("-").str[0],
                                "Basic | Smile_std": manifest["Smile_std"]})
    layouts, summaries, report_anomalies = [], [], []
    identity_audit, reference_smiles = None, None
    for model in config["models"]:
        frame, layout, report_meta = _read_report(folder / model["filename"], model)
        if len(frame) != len(manifest) or frame["No."].tolist() != manifest["vega_row_no"].map(str).tolist():
            raise ValueError(f"Report row count or row numbering differs: {model['filename']}")
        report_smiles = frame["SMILES"].tolist()
        if reference_smiles is None:
            reference_smiles = report_smiles
            identity_audit = _identity_audit(manifest, report_smiles, batch["identity_review_rows"])
        elif report_smiles != reference_smiles:
            raise ValueError(f"Report SMILES order differs across models: {model['filename']}")
        layouts.extend(layout)
        columns = model["quality_columns"] + [p["column"] for p in model["predictions"]]
        block = frame[columns].rename(columns=lambda c: model["name"] + " | " + c)
        predictions = pd.concat([predictions, block], axis=1)
        exception_rows = identity_audit.loc[~identity_audit["identity_verified"], "vega_row_no"]
        for number in exception_rows:
            raw = frame.iloc[number - 1]
            report_anomalies.append({"vega_row_no": number, "qsar_inchikey": manifest.iloc[number - 1]["Qsar_inchikey"],
                                     "model_id": model["id"], "source_file": model["filename"],
                                     "source_sha256": model["sha256"], "source_line_number": int(raw["source_line_number"]),
                                     "raw_report_fields_json": _json(raw.drop(labels="source_line_number").to_dict())})
        summaries.append({"model_id": model["id"], "model_name": model["name"], "source_file": model["filename"],
                          "source_sha256": model["sha256"], "model_metadata": model["model_metadata"],
                          "calculation_metadata": model["calculation_metadata"], "rows": len(frame),
                          "identity_verified_rows": int(identity_audit["identity_verified"].sum()),
                          "identity_review_rows": len(exception_rows),
                          "error_assessment_rows": int(frame["Assessment"].str.contains("[Error]", regex=False).sum()),
                          "adi_provided": "ADI" in model["quality_columns"],
                          "prediction_columns_json": _json(model["predictions"]),
                          "layout_audit_rows": len(layout), **report_meta})
    projections = predictions[["qsar_inchikey", *config["legacy_merge_columns"]]].copy()
    numeric_audit, missing_audit = [], []
    numeric_columns = {m["name"] + " | " + c for m in config["models"] for c in m["numeric_columns"]}
    for column in config["legacy_merge_columns"]:
        if column in numeric_columns:
            continue
        missing = projections[column].isin(config["legacy_excel_missing_tokens"])
        for i in projections.index[missing & projections[column].ne("")]:
            missing_audit.append({"vega_row_no": i + 1, "qsar_inchikey": projections.at[i, "qsar_inchikey"],
                                  "column": column, "raw_value": projections.at[i, column],
                                  "conversion_status": "legacy_excel_na_token_to_missing"})
        projections.loc[missing, column] = pd.NA
    for model in config["models"]:
        for field in model["numeric_columns"]:
            column = model["name"] + " | " + field
            numeric, statuses = _numeric_projection(projections[column])
            for i in statuses.index[statuses.ne("numeric")]:
                numeric_audit.append({"vega_row_no": i + 1, "qsar_inchikey": projections.at[i, "qsar_inchikey"],
                                      "model_id": model["id"], "column": field,
                                      "raw_value": projections.at[i, column], "conversion_status": statuses.at[i]})
            projections[column] = numeric
    mapping = identity_audit[["qsar_inchikey", "vega_row_no", "identity_verified", "identity_status", "reason"]].rename(
        columns={"identity_verified": "qsar_identity_verified", "identity_status": "qsar_identity_status", "reason": "qsar_identity_reason"})
    compounds = identities.compounds.merge(screening.drop(columns=["qsar_inchikey", "representative_record_id"]),
                                           on="inchikey", how="left", validate="one_to_one")
    compounds = compounds.merge(projections, on="qsar_inchikey", how="left", validate="many_to_one").merge(
        mapping, on="qsar_inchikey", how="left", validate="many_to_one")
    compounds["qsar_identity_verified"] = compounds["qsar_identity_verified"].eq(True)
    compounds["qsar_identity_status"] = compounds["qsar_identity_status"].fillna("no_report_association")
    compounds["qsar_identity_reason"] = compounds["qsar_identity_reason"].fillna("")
    compounds["vega_row_no"] = compounds["vega_row_no"].astype("Int64")
    if len(compounds) != len(identities.compounds):
        raise ValueError("QSAR integration changed the number of full chemical identities.")
    affected = compounds.loc[compounds["qsar_identity_status"].eq("review_required"), ["inchikey", "qsar_inchikey", "vega_row_no"]]
    sources = affected.merge(identities.memberships, on="inchikey", how="left", validate="one_to_many").merge(
        identities.records.drop(columns="inchikey").rename(columns={"qsar_inchikey": "record_qsar_inchikey"}),
        on="record_id", how="left", validate="many_to_one")
    for model in config["models"]:
        if _file_hash(folder / model["filename"]) != model["sha256"]:
            raise ValueError(f"Report changed during integration: {model['filename']}")
    if _file_hash(models_path) != config_hash:
        raise ValueError("Model declarations changed during integration.")
    manifest_data = {"schema_version": 1, "policy_version": config["policy_version"], "scope": config["scope"],
        "config_sha256": config_hash, "implementation_sha256": _file_hash(Path(__file__)),
        "identity_policy_version": identities.manifest["policy_version"],
        "upstream_sha256": {"compound_inventory.csv": _frame_hash(identities.compounds),
                            "resolved_records.csv": _frame_hash(identities.records),
                            "compound_memberships.csv": _frame_hash(identities.memberships)},
        "runtime": {"python": platform.python_version(), **{n: version(n) for n in ("rdkit", "pandas", "numpy")}},
        "inputs": [{"filename": m["filename"], "sha256": m["sha256"]} for m in config["models"]],
        "screening_policy": config["screening"], "frozen_batch": batch,
        "known_absent_columns": config["known_absent_columns"],
        "counts": {"compounds": len(compounds), "eligible_compounds": int(screening["keep_for_vega"].sum()),
                   "input_structures": len(manifest), "models": len(config["models"]),
                   "identity_review_inputs": int((~identity_audit["identity_verified"]).sum()),
                   "identity_review_compounds": len(affected), "identity_review_source_records": len(sources)},
        "interpretation": "Historical numerical agreement does not establish chemical correctness. Review-required predictions retain their original values but must not be treated as identity-verified evidence."}
    return QSARResult(screening, manifest, predictions, compounds, identity_audit, sources,
                      pd.DataFrame(report_anomalies, columns=["vega_row_no", "qsar_inchikey", "model_id", "source_file", "source_sha256", "source_line_number", "raw_report_fields_json"]),
                      pd.DataFrame(summaries), pd.DataFrame(layouts, columns=["model_id", "source_file", "source_sha256", "source_line_number", "vega_row_no", "declared_columns", "observed_columns", "layout_action", "raw_cells_json"]),
                      pd.DataFrame(numeric_audit, columns=["vega_row_no", "qsar_inchikey", "model_id", "column", "raw_value", "conversion_status"]),
                      pd.DataFrame(missing_audit, columns=["vega_row_no", "qsar_inchikey", "column", "raw_value", "conversion_status"]), manifest_data)
