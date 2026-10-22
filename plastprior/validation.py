"""Compare identity and QSAR outputs with a fingerprinted historical run without executing it."""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

import pandas as pd

from .inputs import _file_hash


BASELINE = Path(__file__).with_name("identity_baseline.json")
SOURCE_TABLES = {"PlastChem": "plastchem", "UNEP": "unep", "Norman133": "mpleach",
                 "FCCmigex": "fccmigex", "FCChumon_S1": "fcchumon_s1", "FCChumon_S2": "fcchumon_s2",
                 "FCCprio": "fccprio", "LitChemPlast": "litchemplast", "ICCA": "icca",
                 "UCSF": "ucsf", "PlasticMAP": "plasticmap"}
RECORD_FIELDS = {"Smile_std": "smiles_standard", "Smile_isomeric_std": "smiles_isomeric",
                 "Inchikey_std": "inchikey", "Inchikey14": "connectivity_key", "Qsar_inchikey": "qsar_inchikey",
                 "stereo_status": "stereo_status", "Name_std": "name_resolved", "resolved_by": "resolution_route",
                 "confidence_level": "route_tier", "reported_derived_inchikey_status": "reported_derived_status"}
RAW_FIELDS = {"Name": "name_reported", "CAS": "cas_reported", "Smile": "smiles_reported",
              "Inchikey": "inchikey_reported"}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def _verify_hash(path: Path, expected: str) -> None:
    if _file_hash(path) != expected:
        raise ValueError(f"Fingerprint mismatch: {path.name}")


def _record_signature(row: dict) -> tuple:
    # These fields exist both in the old row table and its compound member list.
    fields = ["source_db", *RAW_FIELDS, "Smile_isomeric_std", "Inchikey_std", "Inchikey14",
              "Qsar_inchikey", "stereo_status", "resolved_by", "confidence_level",
              "reported_derived_inchikey_status"]
    return tuple("" if row.get(f) is None else str(row.get(f, "")) for f in fields)


def compare_identity(baseline: str | Path, results: str | Path, output_dir: str | Path) -> dict:
    """Fail on unaccounted differences; compare membership with multiplicity retained.

    Only the documented raw-text bridge and empty-key status clarification are
    permitted. Neither chemical keys nor group membership receive a tolerance.
    """
    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks, boundary_differences = [], [], []

    def check(scope, key, field, expected, actual):
        if expected != actual:
            differences.append({"scope": scope, "key": str(key), "field": field,
                                "expected": str(expected), "actual": str(actual)})

    def compare_columns(scope, old, new, fields, ids):
        for left, right in fields.items():
            for i in old.index[old[left].ne(new[right])]:
                check(scope, ids.loc[i], right, old.at[i, left], new.at[i, right])
        checks.append({"scope": scope, "records": len(old), "fields": len(fields)})

    try:
        declaration = _read_json(BASELINE)
        _verify_hash(baseline / "run_manifest.json", declaration["run_manifest_sha256"])
        run = _read_json(baseline / "run_manifest.json")
        _verify_hash(baseline / "input_manifest.json", run["input_manifest_sha256"])
        baseline_inputs = _read_json(baseline / "input_manifest.json")
        artifacts = {}
        for stage in ("1", "2"):
            entry = run["stages"][stage]
            checkpoint_path = baseline / Path(entry["checkpoint"])
            _verify_hash(checkpoint_path, entry["checkpoint_sha256"])
            checkpoint = _read_json(checkpoint_path)
            for artifact in checkpoint["artifacts"]:
                # Pickles are not loaded; validate the tabular artifacts used below.
                if stage == "2" or artifact["artifact_id"] == "core_identifier_table_csv":
                    path = baseline / Path(artifact["path"])
                    _verify_hash(path, artifact["sha256"])
                    artifacts[artifact["artifact_id"]] = path
        source_manifest = _read_json(results / "source_record_manifest.json")
        identity_manifest = _read_json(results / "identity_manifest.json")
        for manifest in (source_manifest, identity_manifest):
            for name, digest in manifest["output_sha256"].items():
                _verify_hash(results / name, digest)
        _verify_hash(results / "source_records.csv", identity_manifest["source_records_sha256"])
        if identity_manifest["catalog_sha256"] != source_manifest["catalog_sha256"]:
            raise ValueError("Identity and assembly catalogs differ.")
        if identity_manifest["source_assembly_manifest"]["catalog_sha256"] != source_manifest["catalog_sha256"]:
            raise ValueError("Identity input manifest differs from the supplied assembly.")
        old_hashes = {r["filename"]: r["sha256"] for r in baseline_inputs["records"]}
        inputs = source_manifest["input_files"] + identity_manifest["reference_inputs"]
        for item in inputs:
            if item["sha256"] != old_hashes.get(item["filename"]):
                raise ValueError(f"Input differs from the baseline: {item['filename']}")
        if identity_manifest["runtime"]["rdkit"] != run["environment"]["package_versions"]["rdkit"]:
            raise ValueError("RDKit version differs from the baseline.")

        core = _read_csv(artifacts["core_identifier_table_csv"])
        old = _read_csv(artifacts["compound_records_resolved_csv"])
        sources = _read_csv(results / "source_records.csv")
        new = _read_csv(results / "resolved_records.csv")
        if new["record_id"].duplicated().any() or set(new["record_id"]) != set(sources["record_id"]):
            raise ValueError("Resolved records do not preserve a unique link to every source record.")
        preserved = new.set_index("record_id").loc[sources["record_id"]].reset_index()
        compare_columns("raw_record_preservation", sources, preserved,
                        {c: c for c in sources.columns}, sources["record_id"])
        if len(old) != len(core) or not old[list(core.columns)].equals(core):
            raise ValueError("Historical Stage 1 and Stage 2 records are not positionally aligned.")
        new = new.loc[new["included"].eq("True")].copy()
        if set(new["table_id"]) != set(SOURCE_TABLES.values()) or set(old["source_db"]) != set(SOURCE_TABLES):
            raise ValueError("Candidate tables differ from the baseline; row alignment requires review.")
        aligned, old_parts, bridges = [], [], []
        for source, table in SOURCE_TABLES.items():
            prior = old.loc[old["source_db"].eq(source)]
            current = new.loc[new["table_id"].eq(table)].sort_values(
                "source_record_number", key=lambda s: s.astype(int))
            if len(prior) != len(current):
                raise ValueError(f"Cannot align rows: {table} has different record counts.")
            bridges.extend({"record_id": record_id, "baseline_record_number": int(i) + 1,
                            "baseline_source": source, "table_id": table}
                           for record_id, i in zip(current["record_id"], prior.index))
            aligned.append(current)
            old_parts.append(prior)
        new = pd.concat(aligned, ignore_index=True)
        old = pd.concat(old_parts, ignore_index=True)
        bridge = pd.DataFrame(bridges)
        raw_new = new.copy()
        for field in RAW_FIELDS.values():
            raw_new[field] = raw_new[field].str.strip()
        raw_new["cas_reported"] = raw_new["cas_reported"].str.lstrip("'")
        compare_columns("source_assembly", old, raw_new, RAW_FIELDS, new["record_id"])
        if any(d["scope"] == "source_assembly" for d in differences):
            raise ValueError("Source values do not establish the proposed row alignment; review differences.")
        bridge.to_csv(output_dir / "record_alignment.csv", index=False, encoding="utf-8", lineterminator="\n")
        expected = old.copy()
        empty_key = expected["Inchikey_std"].eq("") & expected["Smile_std"].ne("")
        expected.loc[empty_key, "reported_derived_inchikey_status"] = "derived_key_unavailable"
        compare_columns("identity_records", expected, new, RECORD_FIELDS, new["record_id"])
        compare_columns("aggregation_eligibility", old.assign(eligible=old["Inchikey_std"].ne("").map(str)),
                        new, {"eligible": "aggregation_eligible"}, new["record_id"])
        check("status_clarification", "parsed_without_key", "records", declaration["parsed_without_key"], int(empty_key.sum()))

        old_compounds = _read_csv(artifacts["compound_inventory_by_inchikey_csv"])
        compounds = _read_csv(results / "compound_inventory.csv")
        members = _read_csv(results / "compound_memberships.csv")
        if compounds["inchikey"].duplicated().any() or members["record_id"].duplicated().any():
            raise ValueError("Duplicate compound keys or multiply assigned source records.")
        check("compound_keys", "all", "keys", sorted(old_compounds["Inchikey_std"]), sorted(compounds["inchikey"]))
        if set(old_compounds["Inchikey_std"]) != set(compounds["inchikey"]):
            raise ValueError("Compound key sets differ; review before comparing representatives.")
        old_compounds = old_compounds.sort_values("Inchikey_std").reset_index(drop=True)
        compounds = compounds.sort_values("inchikey").reset_index(drop=True)
        # The frozen compound CSV is post-QSAR-QC. Its non-isomeric SMILES
        # was reparsed there; recover the pre-QC value from the recorded member.
        fields = {k: v for k, v in RECORD_FIELDS.items() if k not in {"confidence_level", "Smile_std"}}
        fields.update(best_confidence_level="route_tier", n_records="n_records", CAS="cas_reported")
        compare_columns("compound_representatives", old_compounds, compounds, fields, compounds["inchikey"])
        old_by_id = old.copy()
        old_by_id["record_id"] = new["record_id"]
        old_by_id = old_by_id.set_index("record_id")
        pre_qc_smiles = {}
        for row in old.to_dict("records"):
            pre_qc_smiles.setdefault(_record_signature(row), set()).add(row["Smile_std"])
        expected_members = {rid: key for rid, key in old_by_id["Inchikey_std"].items() if key}
        actual_members = dict(zip(members["record_id"], members["inchikey"]))
        for record_id in sorted(set(expected_members) | set(actual_members)):
            check("membership", record_id, "inchikey", expected_members.get(record_id, ""), actual_members.get(record_id, ""))
        member_groups = {key: group for key, group in members.groupby("inchikey")}
        for prior, current in zip(old_compounds.to_dict("records"), compounds.to_dict("records")):
            key = current["inchikey"]
            group = member_groups.get(key, members.iloc[:0])
            check("membership", key, "n_records", int(current["n_records"]), len(group))
            old_info = json.loads(prior["source_info_json"])
            smiles_candidates = pre_qc_smiles.get(_record_signature(old_info[0]), set())
            if len(smiles_candidates) != 1:
                raise ValueError("Historical representative does not identify an unambiguous pre-QC SMILES.")
            pre_qc = next(iter(smiles_candidates))
            check("compound_pre_qc_structure", key, "smiles_standard", pre_qc, current["smiles_standard"])
            if pre_qc != prior["Smile_std"]:
                boundary_differences.append({"inchikey": key, "legacy_pre_qc_smiles": pre_qc,
                                             "legacy_post_qc_smiles": prior["Smile_std"],
                                             "reason": "Legacy QSAR QC reparsed and rewrote non-isomeric SMILES; deferred to Stage 3."})
            actual_info = [old_by_id.loc[rid].to_dict() for rid in group["record_id"] if rid in old_by_id.index]
            check("membership", key, "source_records_with_multiplicity", Counter(map(_record_signature, old_info)),
                  Counter(map(_record_signature, actual_info)))
            rep_id = current["representative_record_id"]
            if rep_id not in old_by_id.index:
                raise ValueError("Unknown representative record identifier.")
            check("representative_membership", key, "record", _record_signature(old_info[0]),
                  _record_signature(old_by_id.loc[rep_id].to_dict()))
            check("representative_membership", key, "flags", [rep_id],
                  group.loc[group["is_representative"].eq("True"), "record_id"].tolist())
            check("source_membership", key, "tables", sorted(SOURCE_TABLES[s] for s in prior["source_dbs"].split("|")),
                  json.loads(current["source_tables_json"]))
            check("identity_status_sets", key, "statuses", json.loads(prior["reported_derived_inchikey_statuses_json"]),
                  json.loads(current["reported_derived_statuses_json"]))
        checks.append({"scope": "compound_membership_and_representatives", "records": len(compounds), "fields": "all members"})

        prior_cas = _read_csv(artifacts["cas_inchikey_mapping_audit_csv"]).sort_values("CAS").reset_index(drop=True)
        cas = _read_csv(results / "cas_mapping_audit.csv").sort_values("cas").reset_index(drop=True)
        if prior_cas["CAS"].tolist() != cas["cas"].tolist():
            raise ValueError("CAS audit key sets differ.")
        compare_columns("cas_mapping", prior_cas, cas, {"CAS": "cas", "cas_mapping_status": "mapping_status",
                        "cas_mapping_count": "inchikey_count", "cas_connectivity_count": "connectivity_count",
                        "source_record_count": "source_record_count"}, cas["cas"])
        for a, b in zip(prior_cas.to_dict("records"), cas.to_dict("records")):
            for left, right in (("inchikeys_json", "inchikeys_json"), ("inchikey14s_json", "connectivity_keys_json")):
                check("cas_mapping", b["cas"], right, json.loads(a[left]), json.loads(b[right]))
            check("cas_mapping", b["cas"], "source_tables", sorted(SOURCE_TABLES[s] for s in json.loads(a["source_dbs_json"])),
                  json.loads(b["source_tables_json"]))
        report = {"status": "passed" if not differences else "failed", "baseline_run": run["run_id"],
                  "baseline_run_manifest_sha256": declaration["run_manifest_sha256"],
                  "baseline_repository": run["repository"], "baseline_environment": run["environment"],
                  "current_runtime": identity_manifest["runtime"],
                  "identity_manifest_sha256": _file_hash(results / "identity_manifest.json"),
                  "implementation_sha256": _file_hash(Path(__file__)),
                  "source_records_compared": len(new), "compounds_compared": len(compounds),
                  "member_links_compared": len(members), "cas_mappings_compared": len(cas),
                  "input_files_verified": len({r["filename"] for r in inputs}),
                  "documented_status_clarifications": int(empty_key.sum()),
                  "legacy_qsar_qc_smiles_changes": len(boundary_differences),
                  "comparison_policy": "Exact discrete values and member multiplicity; raw text trimmed and CAS leading apostrophes removed only for the legacy bridge. Parsed structures with no key use derived_key_unavailable.",
                  "scope": "Source assembly and identity only. Excludes QSAR QC, prose provenance formatting and later stages. A historical match is not independent scientific validation."}
    except (ValueError, KeyError, OSError) as exc:
        report = {"status": "failed", "error": str(exc)}
    report["unexplained_differences"] = len(differences)
    pd.DataFrame(differences, columns=["scope", "key", "field", "expected", "actual"]).to_csv(
        output_dir / "validation_differences.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(checks, columns=["scope", "records", "fields"]).to_csv(
        output_dir / "validation_checks.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(boundary_differences, columns=["inchikey", "legacy_pre_qc_smiles", "legacy_post_qc_smiles", "reason"]).to_csv(
        output_dir / "stage_boundary_differences.csv", index=False, encoding="utf-8", lineterminator="\n")
    (output_dir / "validation_summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _compare_qsar_frame(expected: pd.DataFrame, actual: pd.DataFrame, key: str, fields: dict,
                        numeric_fields: set[str], scope: str) -> list[dict]:
    """Compare exact text or exact decimal values, including missing-value locations."""
    if expected[key].duplicated().any() or actual[key].duplicated().any():
        raise ValueError(f"Duplicate comparison keys: {scope}")
    if set(expected[key]) != set(actual[key]):
        raise ValueError(f"Comparison key sets differ: {scope}")
    expected = expected.set_index(key).sort_index()
    actual = actual.set_index(key).loc[expected.index]
    differences = []
    for left, right in fields.items():
        for row_key in expected.index[expected[left].ne(actual[right])]:
            a, b = expected.at[row_key, left], actual.at[row_key, right]
            if right in numeric_fields and a != "" and b != "":
                try:
                    if Decimal(a) == Decimal(b):
                        continue
                except InvalidOperation:
                    pass
            differences.append({"scope": scope, "key": row_key, "field": right, "expected": a, "actual": b})
    return differences


def compare_qsar(baseline: str | Path, results: str | Path, output_dir: str | Path,
                 upstream_results: str | Path | None = None) -> dict:
    """Validate Stage 3A against the frozen run, explicitly excluding Pov/LRTP."""
    from .qsar import DEFAULT_MODELS

    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    upstream = Path(upstream_results) if upstream_results is not None else results.parent / "stage2"
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks = [], []

    def compare(old, new, key, fields, numeric, scope):
        differences.extend(_compare_qsar_frame(old, new, key, fields, numeric, scope))
        checks.append({"scope": scope, "rows": len(old), "fields": len(fields)})

    try:
        upstream_report = compare_identity(baseline, upstream, output_dir / "stage2")
        if upstream_report["status"] != "passed":
            raise ValueError("Upstream Stage 2 regression failed; inspect the nested report.")
        run = _read_json(baseline / "run_manifest.json")
        artifacts = {}
        checkpoints = {}
        for number in ("2", "3"):
            entry = run["stages"][number]
            path = baseline / Path(entry["checkpoint"])
            _verify_hash(path, entry["checkpoint_sha256"])
            cp = _read_json(path)
            checkpoints[number] = cp
            for item in cp["artifacts"]:
                path = baseline / Path(item["path"])
                _verify_hash(path, item["sha256"])
                artifacts[item["artifact_id"]] = path
        current_manifest = _read_json(results / "qsar_manifest.json")
        _verify_hash(DEFAULT_MODELS, current_manifest["config_sha256"])
        config = _read_json(DEFAULT_MODELS)
        for name, digest in current_manifest["output_sha256"].items():
            _verify_hash(results / name, digest)
        for name, digest in current_manifest["upstream_sha256"].items():
            _verify_hash(upstream / name, digest)
        old_reports = _read_csv(artifacts["vega_report_manifest_csv"])
        if {r["filename"]: r["sha256"] for r in current_manifest["inputs"]} != dict(zip(old_reports["source_file"], old_reports["source_sha256"])):
            raise ValueError("Frozen report fingerprints differ from the historical batch.")
        if current_manifest["runtime"]["rdkit"] != run["environment"]["package_versions"]["rdkit"]:
            raise ValueError("RDKit version differs from the reference run.")

        old_qc = _read_csv(artifacts["compound_inventory_by_inchikey_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        old_record_qc = _read_csv(artifacts["compound_records_qc_csv"])
        weights = old_record_qc.loc[old_record_qc["Inchikey_std"].ne(""), ["Inchikey_std", "MW"]].drop_duplicates()
        if weights["Inchikey_std"].duplicated().any():
            raise ValueError("Historical compound molecular weights are inconsistent across member rows.")
        old_qc = old_qc.merge(weights.rename(columns={"Inchikey_std": "inchikey"}), on="inchikey", validate="one_to_one")
        screening = _read_csv(results / "qsar_screening.csv")
        compare(old_qc, screening, "inchikey", {"Smile_std": "qsar_smiles", "Qsar_inchikey": "qsar_inchikey",
                "keep_for_vega": "keep_for_vega", "qc_flags": "qc_flags", "MW": "molecular_weight"},
                {"molecular_weight"}, "structure_screening")
        old_comments = old_record_qc.loc[old_record_qc["Inchikey_std"].ne(""), ["Inchikey_std", "comment"]].drop_duplicates()
        compare(old_comments.rename(columns={"Inchikey_std": "inchikey"}), screening, "inchikey",
                {"comment": "exclusion_reason"}, set(), "screening_reasons")
        old_input = _read_csv(artifacts["vega_input_row_manifest_csv"])
        new_input = _read_csv(results / "vega_input_row_manifest.csv")
        compare(old_input, new_input, "vega_row_no", {c: c for c in old_input.columns if c != "vega_row_no"}, set(), "input_manifest")
        if _file_hash(results / "vega_input_smiles.txt") != _file_hash(artifacts["vega_input_smiles_txt"]):
            raise ValueError("VEGA input SMILES bytes differ from the baseline.")

        old_master = pd.read_excel(artifacts["vega_master_xlsx"], sheet_name="VEGA_DATA", dtype=str,
                                   keep_default_na=False, engine="openpyxl").rename(columns={"Inchikey": "qsar_inchikey"})
        predictions = _read_csv(results / "qsar_predictions.csv")
        if set(old_master.columns) != set(predictions.columns):
            raise ValueError("Parsed prediction/quality fields differ from the frozen master.")
        compare(old_master, predictions, "qsar_inchikey", {c: c for c in old_master if c != "qsar_inchikey"}, set(), "raw_model_values")
        old_merged = _read_csv(artifacts["compound_inventory_with_qsar_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        merged = _read_csv(results / "compound_qsar.csv")
        if any(c.startswith("LRTP_") for c in merged):
            raise ValueError("Stage 3A must not emit Pov/LRTP calculation fields.")
        fields = config["legacy_merge_columns"]
        numeric = {m["name"] + " | " + c for m in config["models"] for c in m["numeric_columns"]}
        compare(old_merged, merged, "inchikey", {c: c for c in fields}, numeric, "compound_qsar_values")
        source_compounds = _read_csv(upstream / "compound_inventory.csv")
        compare(source_compounds, merged, "inchikey", {c: c for c in source_compounds if c != "inchikey"}, set(), "upstream_identity_preservation")

        audit = _read_csv(results / "qsar_identity_audit.csv")
        if audit["vega_row_no"].tolist() != new_input["vega_row_no"].tolist() or audit["qsar_inchikey"].tolist() != new_input["Qsar_inchikey"].tolist():
            raise ValueError("Identity audit is not aligned with the full input manifest.")
        exceptions = audit.loc[audit["identity_verified"].eq("False")]
        if exceptions["vega_row_no"].astype(int).tolist() != config["frozen_batch"]["identity_review_rows"]:
            raise ValueError("Identity-review rows differ from the frozen declaration.")
        expected_flags = merged["qsar_inchikey"].map(audit.set_index("qsar_inchikey")["identity_verified"]).fillna("False")
        if not expected_flags.equals(merged["qsar_identity_verified"]):
            raise ValueError("Compound identity-verification flags do not match the input audit.")
        expected_states = merged["qsar_inchikey"].map(audit.set_index("qsar_inchikey")["identity_status"]).fillna("no_report_association")
        if not expected_states.equals(merged["qsar_identity_status"]):
            raise ValueError("Compound identity-review statuses differ from the audit.")
        model_summary = _read_csv(results / "qsar_model_summary.csv")
        compare(old_reports, model_summary.rename(columns={"source_file": "source_file"}), "source_file",
                {"raw_rows": "rows", "report_smiles_key_matches": "identity_verified_rows",
                 "report_smiles_key_mismatches": "identity_review_rows"}, set(), "model_identity_counts")
        refs = _read_csv(results / "identity_anomaly_reports.csv")
        expected_pairs = {(str(n), m["id"]) for n in config["frozen_batch"]["identity_review_rows"] for m in config["models"]}
        if len(refs) != len(expected_pairs) or set(zip(refs["vega_row_no"], refs["model_id"])) != expected_pairs:
            raise ValueError("Incomplete or duplicated anomaly-to-report provenance.")
        expected_hashes = {m["id"]: m["sha256"] for m in config["models"]}
        if not refs["model_id"].map(expected_hashes).equals(refs["source_sha256"]):
            raise ValueError("Anomaly report provenance has mismatched source fingerprints.")
        links = _read_csv(results / "identity_anomaly_sources.csv")
        members = _read_csv(upstream / "compound_memberships.csv")
        affected_keys = set(merged.loc[merged["qsar_identity_status"].eq("review_required"), "inchikey"])
        expected_links = members.loc[members["inchikey"].isin(affected_keys)]
        if Counter(zip(links["inchikey"], links["record_id"])) != Counter(zip(expected_links["inchikey"], expected_links["record_id"])):
            raise ValueError("Identity exceptions do not retain every original source member.")
        original = _read_csv(upstream / "resolved_records.csv").set_index("record_id").loc[links["record_id"]].reset_index()
        provenance_fields = ["source_id", "table_id", "source_filename", "source_sha256", "source_record_number",
                             "source_native_id", "reported_fields_json", "selected_reference_id", "selected_reference_table"]
        compare(original, links, "record_id", {c: c for c in provenance_fields}, set(), "anomaly_source_provenance")
        summary = {"status": "passed" if not differences else "failed", "scope": "Stage 3A only; Pov/LRTP excluded",
                   "baseline_run": run["run_id"], "baseline_run_manifest_sha256": _file_hash(baseline / "run_manifest.json"),
                   "qsar_manifest_sha256": _file_hash(results / "qsar_manifest.json"),
                   "implementation_sha256": _file_hash(Path(__file__)), "upstream_regression": "passed",
                   "compounds_compared": len(merged), "input_rows_compared": len(new_input),
                   "model_value_columns_compared": len(old_master.columns) - 1,
                   "compound_qsar_columns_compared": len(fields), "identity_review_inputs": len(exceptions),
                   "anomaly_report_links": len(refs), "anomaly_source_records": len(links),
                   "scientific_identity_review": "pending", "numeric_comparison": "Exact decimal values; no floating-point tolerance",
                   "interpretation": "Reproduces frozen associations and values; does not validate the chemical correctness of review-required mappings."}
    except (ValueError, KeyError, OSError) as exc:
        summary = {"status": "failed", "error": str(exc), "scope": "Stage 3A only"}
    summary["unexplained_differences"] = len(differences)
    pd.DataFrame(differences, columns=["scope", "key", "field", "expected", "actual"]).to_csv(
        output_dir / "qsar_validation_differences.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(checks, columns=["scope", "rows", "fields"]).to_csv(
        output_dir / "qsar_validation_checks.csv", index=False, encoding="utf-8", lineterminator="\n")
    (output_dir / "qsar_validation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Frozen historical run directory.")
    parser.add_argument("--results", type=Path, required=True, help="Current report directory for the selected stage.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Validation report directory.")
    parser.add_argument("--stage", choices=["identity", "qsar"], default="identity")
    parser.add_argument("--upstream-results", type=Path, help="Stage 2 outputs for QSAR validation; defaults to sibling stage2.")
    args = parser.parse_args(argv)
    report = (compare_qsar(args.baseline, args.results, args.output_dir, args.upstream_results)
              if args.stage == "qsar" else compare_identity(args.baseline, args.results, args.output_dir))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
