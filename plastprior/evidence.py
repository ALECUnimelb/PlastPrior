"""Assemble Stage 4A source evidence with explicit selection and identity isolation."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import platform
import warnings

import pandas as pd

from .inputs import DEFAULT_CATALOG, _file_hash, load_catalog, resolve_data_root
from .lrtp import VALUE_COLUMNS, _verify_outputs
from ._evidence_rules import (unify_compound_record, make_slim_record, iter_audit_rows,
                              _build_classification_outputs, _json_default, CLASSIFICATION_OUTPUT_COLUMNS)

DEFAULT_FIELDS = Path(__file__).with_name("evidence_fields.json")
FIELDS_HASH = _file_hash(DEFAULT_FIELDS)
RAW_FIELDS = {"Inchikey": "inchikey_reported", "CAS": "cas_reported", "Smile": "smiles_reported", "Name": "name_reported"}
HISTORICAL_EVENT_FIELDS = ["compound_key", "status", "field_path", "db", "row_index", "match_type",
                          "match_col", "match_value", "source_col", "raw_value", "selected", "reason"]


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default, allow_nan=False)


def _read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def _normal(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return None if not text or text.lower() in {"nan", "none", "null"} else text


def _best_column(columns, candidates):
    normal = lambda s: str(s).strip().lower().replace(" ", "").replace("_", "")
    lookup = {normal(c): c for c in columns}
    return next((lookup[normal(c)] for c in candidates if normal(c) in lookup), None)


def _clean_row(row):
    return {str(k): None if pd.isna(v) else v.item() if hasattr(v, "item") else v for k, v in row.items()}


def _load_tables(data_root, catalog, config, records):
    declarations = {t["id"]: (s, t) for s in catalog["sources"] for t in s["tables"]}
    tables, metadata, mappings, notices = {}, {}, [], []
    for label, table_id in config["source_labels"].items():
        source, table = declarations[table_id]
        path = resolve_data_root(data_root) / "SourceDatabase" / source["filename"]
        digest = _file_hash(path)
        source_records = records.loc[records["table_id"].eq(table_id)]
        if set(source_records["source_sha256"]) != {digest}:
            raise ValueError(f"Source does not match Stage 2 provenance: {table_id}")
        with warnings.catch_warnings(record=True) as notes:
            warnings.simplefilter("always")
            options = {"header": table["header"], "keep_default_na": True}
            if path.suffix.lower() == ".csv":
                frame = pd.read_csv(path, encoding="utf-8", **options)
            else:
                frame = pd.read_excel(path, sheet_name=table["sheet"],
                                      engine="xlrd" if path.suffix.lower() == ".xls" else "openpyxl", **options)
        if _file_hash(path) != digest or len(frame) != len(source_records):
            raise ValueError(f"Source bytes or row count differ from Stage 2: {table_id}")
        if frame.columns.duplicated().any():
            raise ValueError(f"Duplicate source column labels: {table_id}")
        tables[label] = frame
        metadata[label] = {"source_id": source["id"], "table_id": table_id, "source_filename": path.name,
                           "source_sha256": digest, "source_sheet": table["sheet"], "header_row": table["header"] + 1}
        notices.append({**metadata[label], "reader_policy": "historical_pandas_type_inference_default_na", "rows": len(frame),
                        "reader_warnings": "; ".join(dict.fromkeys(str(n.message) for n in notes))})
        for match_type, candidates in config["matching"]["columns"].items():
            selected = _best_column(frame.columns, candidates)
            mappings.append({"source": label, "table_id": table_id, "match_type": match_type,
                             "selected_column": selected, "candidate_columns_json": _json(candidates),
                             "comparison": config["matching"]["comparison"]})
    return tables, metadata, pd.DataFrame(mappings), pd.DataFrame(notices)


def _field_mapping(config, tables):
    rules = config["field_rules"]
    groups = {"identity_cols": "identity", "hazard_cols": "hazard", "human_cols": "exposure.human",
              "migration_cols": "exposure.migration", "production_cols": "exposure.production",
              "environment_cols": "exposure.environment", "patent_cols": "exposure.patent",
              "literature_cols": "exposure.literature", "reg_top_cols": "regulatory_listings",
              "classification_cols": "classification"}
    rows = []
    def add(label, field, column, rule, conversion):
        rows.append({"source": label, "field_path": field, "source_column": column,
                     "column_present": column in tables[label], "selection_rule": rule, "conversion": conversion})
    for label in tables:
        for group, root in groups.items():
            for field, mapping in rules[group].items():
                for col in mapping.get(label, []) + mapping.get("*", []):
                    conversion = ("numeric_or_missing" if group in {"production_cols", "literature_cols"} or field == "monoisotopic_mass"
                                  else "uppercase_trim" if field == "inchikey" else "trim" if group == "identity_cols" else "preserve_source_value")
                    add(label, root + "." + field, col,
                        "first_by_declared_source_priority" if group == "identity_cols" else "distinct_values_with_all_observation_links", conversion)
        for col in rules["tox_label_cols"].get(label, []) + rules["tox_label_cols"].get("*", []):
            add(label, "hazard.toxicological_labels", col, "distinct_values_with_all_observation_links", "preserve_source_value")
        if label == "PlastChem":
            special = {"global_agreement_keys": ("regulatory_listings.plastchem.global_agreements", "truthy_membership"),
                       "regional_summary_keys": ("regulatory_listings.plastchem.regional_summaries", "truthy_membership"),
                       "specific_reg_keys": ("regulatory_listings.plastchem.specific_regulations", "truthy_membership"),
                       "plastchem_polymer_columns": ("classification.plastchem.polymer_context", "numeric_last_valid_row"),
                       "plastchem_structural_group_columns": ("classification.plastchem.structural_groups", "truthy_membership"),
                       "plastchem_concern_columns": ("classification.plastchem.concern", "last_nonmissing_value_with_list_truth_filter")}
            for name, (field, rule) in special.items():
                for col in rules[name]: add(label, field, col, rule, "source_annotation_not_PlastPrior_score")
            for col in [rules["scope_mea_key"], rules["scope_precedent_key"]]:
                add(label, "regulatory_listings.plastchem.scope", col, "truthy_membership", "global_or_regional_label")
            add(label, "classification.plastchem.functions", "Harmonized_functions", "ordered_unique_functions", "semicolon_split_and_declared_top_class_mapping")
            for field, col in [("use", "Use"), ("presence", "Presence"), ("release", "Release")]:
                add(label, "classification.plastchem.upr." + field, col, "truthy_membership", "source_annotation")
    return pd.DataFrame(rows)


def _classification_decisions(bundle, rejected, config, key, provenance):
    """Audit the historical last-valid-row rule, including values absent from its field audit."""
    rows = sorted(bundle["per_db"].get("PlastChem", {}).get("matches", []), key=lambda m: m["row_index"])
    decisions = []
    last = {}
    for match in rows:
        index = match["row_index"]
        rejection = rejected.get(("PlastChem", index, match["match_type"], match["match_value"]))
        for group, field in (("plastchem_polymer_columns", "polymer_context"), ("plastchem_concern_columns", "concern")):
            for column in config["field_rules"][group]:
                raw = match["data"].get(column)
                value = raw
                reason = "selected_last_valid_row"
                if rejection:
                    reason = "excluded_identity_mismatch"
                elif raw is None or isinstance(raw, str) and not raw.strip():
                    reason = "missing_source_value"
                elif field == "polymer_context":
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        reason = "invalid_numeric_value"
                elif column.endswith("_list") or column in {"Red_list", "Orange_list", "Watch_list", "White_list", "Grey_list"}:
                    truth = raw.strip().lower() in {"1", "true", "t", "yes", "y", "present", "listed", "positive"} if isinstance(raw, str) else bool(raw)
                    if not truth:
                        reason = "not_selected_nonpositive_list_annotation"
                event = {"compound_key": key, "source_record_id": provenance["PlastChem", index]["record_id"],
                         "source_sha256": provenance["PlastChem", index]["source_sha256"],
                         "field_path": "classification.plastchem." + field + "." + column,
                         "source_column": column, "raw_value": raw, "normalized_value": value,
                         "selected": reason == "selected_last_valid_row", "selection_reason": reason,
                         "match_type": match["match_type"], "match_value": match["match_value"], "row_index": index}
                if event["selected"]:
                    prior = last.get(event["field_path"])
                    if prior is not None:
                        decisions[prior].update(selected=False, selection_reason="superseded_by_later_valid_row")
                    last[event["field_path"]] = len(decisions)
                decisions.append(event)
    for field in ("polymer_context", "concern"):
        selected = [decisions[i] for path, i in last.items() if path.startswith("classification.plastchem." + field + ".")]
        if selected and all(not e["normalized_value"] for e in selected):
            for event in selected:
                event.update(selected=False, selection_reason="omitted_all_zero_block_historical_rule")
    return decisions


@dataclass
class EvidenceResult:
    compounds: pd.DataFrame
    historical: pd.DataFrame
    attempts: list
    candidates: list
    events: list
    classification_decisions: list
    isolation: pd.DataFrame
    field_mapping: pd.DataFrame
    match_mapping: pd.DataFrame
    source_summary: pd.DataFrame
    tables: dict
    row_provenance: dict
    used_rows: set
    manifest: dict

    def write_reports(self, output_dir):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in (("compound_evidence", self.compounds), ("basic_evidence_historical", self.historical),
                            ("prediction_isolation_audit", self.isolation), ("evidence_field_mapping", self.field_mapping),
                            ("evidence_match_mapping", self.match_mapping), ("evidence_source_summary", self.source_summary)):
            path = folder / (name + ".csv")
            frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            outputs[path.name] = _file_hash(path)
        raw_rows = ({**self.row_provenance[label, index], "raw_fields": _clean_row(self.tables[label].iloc[index])}
                    for label, index in sorted(self.used_rows))
        for name, rows in (("evidence_match_attempts", self.attempts), ("evidence_candidates", self.candidates),
                           ("basic_evidence_audit", self.events), ("classification_selection_audit", self.classification_decisions),
                           ("evidence_source_rows", raw_rows)):
            path = folder / (name + ".jsonl")
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                for row in rows: stream.write(_json(row) + "\n")
            outputs[path.name] = _file_hash(path)
        (folder / "evidence_manifest.json").write_text(json.dumps({**self.manifest, "output_sha256": outputs}, indent=2) + "\n", encoding="utf-8")


def isolate_predictions(compounds, config):
    """Mask model-specific fields while retaining independent database observations."""
    output = compounds.copy()
    review = output["qsar_identity_status"].eq("review_required")
    fields = [c for c in config["legacy_merge_columns"] if not c.startswith("Basic | ")]
    if set(fields) - set(output): raise ValueError("Missing declared QSAR projection fields.")
    if "LRTP_evidence" in output: raise ValueError("Historical LRTP evidence cannot enter the analysis table.")
    if output.loc[review, VALUE_COLUMNS].ne("").any().any():
        raise ValueError("Stage 3B has not isolated all identity-review LRTP values.")
    if not output.loc[review, "lrtp_available"].eq("False").all():
        raise ValueError("Identity-review LRTP evidence is incorrectly available.")
    audits = []
    for row in output.loc[review].to_dict("records"):
        for col in [*fields, *VALUE_COLUMNS]:
            audits.append({"inchikey": row["inchikey"], "qsar_inchikey": row["qsar_inchikey"],
                           "vega_row_no": row["vega_row_no"], "field": col, "upstream_value": row[col],
                           "analysis_value": "", "action": "already_isolated_in_stage3b" if col in VALUE_COLUMNS else "withheld_qsar_value",
                           "exclusion_reason": "identity_review_required", "identity_reason": row["qsar_identity_reason"]})
    output.loc[review, fields] = ""
    output["qsar_evidence_available"] = output["qsar_identity_verified"].eq("True")
    return output, pd.DataFrame(audits)


def integrate_evidence(stage2_results, lrtp_results, data_root="data"):
    """Build only basic source evidence; no specialist resolvers or later scores."""
    stage2, lrtp = Path(stage2_results), Path(lrtp_results)
    config = json.loads(DEFAULT_FIELDS.read_text(encoding="utf-8"))
    if config["schema_version"] != 1 or _file_hash(DEFAULT_FIELDS) != FIELDS_HASH:
        raise ValueError("Evidence field policy changed; restart the process.")
    manifests, fingerprints = {}, {}
    for name, folder, filename in (("identity", stage2, "identity_manifest.json"),
                                   ("lrtp", lrtp, "lrtp_manifest.json"), ("qsar", lrtp.parent, "qsar_manifest.json")):
        path = folder / filename
        fingerprints[name] = _file_hash(path)
        manifests[name] = json.loads(path.read_text(encoding="utf-8"))
        _verify_outputs(folder, manifests[name])
    if manifests["lrtp"]["upstream_qsar_manifest_sha256"] != fingerprints["qsar"]:
        raise ValueError("LRTP artifacts refer to a different QSAR run.")
    for filename, digest in manifests["qsar"]["upstream_sha256"].items():
        if _file_hash(stage2 / filename) != digest: raise ValueError("QSAR and identity artifacts differ.")
    catalog = load_catalog()
    if _file_hash(DEFAULT_CATALOG) != manifests["identity"]["catalog_sha256"]:
        raise ValueError("Source catalog differs from Stage 2.")
    records = _read_csv(stage2 / "resolved_records.csv")
    members = _read_csv(stage2 / "compound_memberships.csv")
    compounds = _read_csv(lrtp / "compound_lrtp.csv")
    if compounds["inchikey"].duplicated().any() or members["record_id"].duplicated().any():
        raise ValueError("Duplicate identities or multiply assigned source records.")
    tables, metadata, match_mapping, source_summary = _load_tables(data_root, catalog, config, records)
    labels = {v: k for k, v in config["source_labels"].items()}
    provenance = {}
    for row in records.to_dict("records"):
        label = labels[row["table_id"]]
        provenance[label, int(row["source_record_number"]) - 1] = {k: row[k] for k in (
            "record_id", "source_id", "table_id", "source_filename", "source_sha256", "source_sheet",
            "source_record_number", "source_row_number", "source_native_id", "reported_fields_json")}
    member_rows = members.merge(records.drop(columns="inchikey"), on="record_id", how="left", validate="one_to_one")
    groups = {k: g.to_dict("records") for k, g in member_rows.groupby("inchikey", sort=False)}
    if set(groups) != set(compounds["inchikey"]): raise ValueError("Evidence membership does not cover the full inventory.")
    indexes, selected_cols = {}, {}
    for label, frame in tables.items():
        selected_cols[label] = {}
        for rule in match_mapping.loc[match_mapping["source"].eq(label)].to_dict("records"):
            col = _normal(rule["selected_column"])
            selected_cols[label][rule["match_type"]] = col
            if col:
                index = defaultdict(list)
                for i, value in enumerate(frame[col].astype(str).str.strip().str.upper()): index[value].append(i)
                indexes[label, col] = index
    @lru_cache(maxsize=5000)
    def source_row(label, index): return _clean_row(tables[label].iloc[index])
    attempts, candidates, events, summaries, used_rows = [], [], [], [], set()
    decisions = []
    for key in compounds["inchikey"]:
        bundle = {"per_db": {}}
        links = defaultdict(list)
        compound_attempts = []
        # Preserve stable Stage 2 member order, then group by database as in the historical collector.
        by_db = defaultdict(list)
        for row in groups[key]: by_db[labels[row["table_id"]]].append(row)
        for label, queries in by_db.items():
            bundle["per_db"][label] = {"matches": []}
            for number, query in enumerate(queries):
                query_index = int(query["source_record_number"]) - 1
                used_rows.add((label, query_index))
                raw = {k: _normal(query[v].strip().lstrip("'") if k == "CAS" else query[v]) for k, v in RAW_FIELDS.items()}
                plan = [(kind, selected_cols[label][kind], raw[field]) for kind, field in
                        (("inchikey", "Inchikey"), ("cas", "CAS"), ("smiles", "Smile"))
                        if selected_cols[label][kind] and raw[field]]
                tried, hits, method, column, value = [], [], None, None, None
                for method, column, value in plan:
                    hits = indexes[label, column].get(value.upper(), [])
                    tried.append({"match_type": method, "column": column, "value": value, "hit_count": len(hits)})
                    if hits: break
                attempt_id = key + ":" + query["record_id"]
                attempt = {"compound_key": key, "attempt_id": attempt_id, "query_record_id": query["record_id"],
                           "db": label, "query_fields": raw, "search_plan": plan, "attempted_queries": tried,
                           "hit_count": len(hits), "picked_source_record_id": provenance[label, hits[0]]["record_id"] if hits else None,
                           "selection_reason": "first_matching_source_row" if hits else "no_match" if plan else "no_usable_index"}
                attempts.append(attempt);compound_attempts.append(attempt)
                for position, index in enumerate(hits):
                    used_rows.add((label, index))
                    candidate = {"compound_key": key, "attempt_id": attempt_id, "query_record_id": query["record_id"],
                                 "db": label, "row_index": index, "record_id": provenance[label, index]["record_id"],
                                 "match_type": method, "match_col": column, "match_value": value,
                                 "selected_for_identity_check": position == 0,
                                 "selection_reason": "first_matching_source_row" if position == 0 else "not_selected_first_row_policy"}
                    candidates.append(candidate)
                    if position == 0:
                        bundle["per_db"][label]["matches"].append({"attempt_id": number, "match_type": method,
                            "match_col": column, "match_value": value, "row_index": index, "data": source_row(label, index)})
                        links[label, index, method, column, value].append(query["record_id"])
        unified = unify_compound_record(bundle)
        slim = make_slim_record(unified)
        summaries.append({"inchikey": key, "db_extract_info": _json(slim), **_build_classification_outputs(slim)})
        rejected = {(m["db"], m["row_index"], m["match_type"], m.get("match_value")): m["reason"] for m in unified["mismatch_report"]}
        decisions.extend(_classification_decisions(bundle, rejected, config, key, provenance))
        for attempt in compound_attempts:
            if attempt["picked_source_record_id"]:
                last = attempt["attempted_queries"][-1]
                idx = next(i for i in indexes[attempt["db"], last["column"]][last["value"].upper()])
                reason = rejected.get((attempt["db"], idx, last["match_type"], last["value"]))
                attempt["identity_gate_status"] = "rejected" if reason else "accepted_by_historical_rule"
                attempt["identity_gate_reason"] = reason or ("smiles_text_match_is_not_identity_proof" if last["match_type"] == "smiles" else "matches_historical_identity_seed")
            else:
                attempt["identity_gate_status"] = "not_evaluated"
                attempt["identity_gate_reason"] = attempt["selection_reason"]
        for event in iter_audit_rows(unified, compound_key=key):
            label, index = event["db"], int(event["row_index"])
            ident = (label, index, event["match_type"], event["match_col"] or event["source_col"], event["match_value"])
            status = ("excluded_identity_mismatch" if event["status"] == "mismatch" else
                      "selected_source_priority" if event.get("selected") is True else
                      "not_selected_source_priority" if event.get("selected") is False else "retained_source_observation")
            events.append({**event, "source_record_id": provenance[label, index]["record_id"],
                           "source_sha256": metadata[label]["source_sha256"],
                           "query_record_ids": links[ident], "selection_reason": status})
    historical = pd.DataFrame(summaries)
    qsar_config_path = Path(__file__).with_name("qsar_models.json")
    if _file_hash(qsar_config_path) != manifests["qsar"]["config_sha256"]:
        raise ValueError("QSAR field declarations differ from Stage 3A.")
    available, isolation = isolate_predictions(compounds, json.loads(qsar_config_path.read_text(encoding="utf-8")))
    available = available.merge(historical, on="inchikey", how="left", validate="one_to_one")
    for label, meta in metadata.items():
        if _file_hash(resolve_data_root(data_root) / "SourceDatabase" / meta["source_filename"]) != meta["source_sha256"]:
            raise ValueError("A source changed during evidence integration.")
    for name, folder, filename in (("identity", stage2, "identity_manifest.json"), ("lrtp", lrtp, "lrtp_manifest.json"),
                                   ("qsar", lrtp.parent, "qsar_manifest.json")):
        if _file_hash(folder / filename) != fingerprints[name]: raise ValueError("Upstream manifest changed during integration.")
        _verify_outputs(folder, manifests[name])
    if _file_hash(DEFAULT_FIELDS) != FIELDS_HASH: raise ValueError("Field policy changed during integration.")
    counts = {"compounds": len(compounds), "source_member_attempts": len(attempts), "matched_candidates": len(candidates),
              "retained_source_rows": len(used_rows), "historical_audit_events": len(events),
              "identity_mismatch_events": sum(e["status"] == "mismatch" for e in events),
              "identity_review_compounds": int(compounds["qsar_identity_status"].eq("review_required").sum()),
              "isolated_prediction_fields": len(isolation), "classification_decisions": len(decisions)}
    manifest = {"schema_version": 1, "policy_version": config["policy_version"], "scope": config["scope"],
                "config_sha256": FIELDS_HASH, "implementation_sha256": _file_hash(Path(__file__)),
                "rules_sha256": _file_hash(Path(__file__).with_name("_evidence_rules.py")),
                "catalog_sha256": _file_hash(DEFAULT_CATALOG), "upstream_manifests_sha256": fingerprints,
                "inputs": list(metadata.values()), "counts": counts,
                "runtime": {"python": platform.python_version(), "pandas": pd.__version__},
                "historical_sources": config["historical_sources"], "interpretation": config["interpretation"]}
    return EvidenceResult(available, historical, attempts, candidates, events, decisions, isolation,
                          _field_mapping(config, tables), match_mapping, source_summary, tables, provenance, used_rows, manifest)
