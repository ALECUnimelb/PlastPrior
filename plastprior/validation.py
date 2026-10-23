"""Compare identity and QSAR outputs with a fingerprinted historical run without executing it."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
import io
import tempfile
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


def _compare_evidence(expected: str, actual: str, key: str) -> list[dict]:
    """Compare nested evidence, retaining types, list order and exact decimal numbers."""
    left = json.loads(expected, parse_float=Decimal, parse_int=Decimal)
    right = json.loads(actual, parse_float=Decimal, parse_int=Decimal)
    differences = []

    def visit(a, b, field):
        if isinstance(a, dict) and isinstance(b, dict):
            for name in sorted(set(a) | set(b)):
                if name not in a or name not in b:
                    differences.append({"scope": "historical_evidence", "key": key, "field": field + "." + name,
                                        "expected": repr(a.get(name, "<absent>")), "actual": repr(b.get(name, "<absent>"))})
                else:
                    visit(a[name], b[name], field + "." + name)
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                visit(x, y, f"{field}[{i}]")
        elif type(a) is not type(b) or a != b:
            differences.append({"scope": "historical_evidence", "key": key, "field": field,
                                "expected": repr(a), "actual": repr(b)})
    visit(left, right, "LRTP_evidence")
    return differences


def compare_lrtp(baseline: str | Path, results: str | Path, output_dir: str | Path,
                 upstream_results: str | Path | None = None) -> dict:
    """Check all historical LRTP fields and the separate identity-isolation contract."""
    from .lrtp import DEFAULT_PARAMETERS, LRTP_OUTPUT_COLUMNS, VALUE_COLUMNS, LRTP_REQUIRED_PREDICTION_COLUMNS
    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    upstream = Path(upstream_results) if upstream_results is not None else results.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks = [], []

    def compare(old, new, key, fields, numeric, scope):
        differences.extend(_compare_qsar_frame(old, new, key, fields, numeric, scope))
        checks.append({"scope": scope, "rows": len(old), "fields": len(fields)})

    try:
        prior = compare_qsar(baseline, upstream, output_dir / "stage3a")
        if prior["status"] != "passed":
            raise ValueError("Stage 3A regression failed; inspect the nested report.")
        manifest = _read_json(results / "lrtp_manifest.json")
        _verify_hash(DEFAULT_PARAMETERS, manifest["parameters_sha256"])
        _verify_hash(Path(__file__).with_name("lrtp.py"), manifest["implementation_sha256"])
        _verify_hash(upstream / "qsar_manifest.json", manifest["upstream_qsar_manifest_sha256"])
        qsar_manifest = _read_json(upstream / "qsar_manifest.json")
        if manifest["upstream_output_sha256"] != qsar_manifest["output_sha256"]:
            raise ValueError("Stage 3B fingerprints do not describe the validated Stage 3A outputs.")
        for name, digest in manifest["output_sha256"].items():
            _verify_hash(results / name, digest)
        run = _read_json(baseline / "run_manifest.json")
        entry = run["stages"]["3"]
        _verify_hash(baseline / entry["checkpoint"], entry["checkpoint_sha256"])
        checkpoint = _read_json(baseline / entry["checkpoint"])
        artifacts = {}
        for item in checkpoint["artifacts"]:
            path = baseline / item["path"]
            _verify_hash(path, item["sha256"])
            artifacts[item["artifact_id"]] = path
        old = _read_csv(artifacts["lrtp_results_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        history = _read_csv(results / "lrtp_historical_results.csv")
        source = _read_csv(upstream / "compound_qsar.csv")
        analysis = _read_csv(results / "compound_lrtp.csv")
        numeric = set(LRTP_OUTPUT_COLUMNS[:9])
        fields = {c: c for c in LRTP_OUTPUT_COLUMNS if c != "LRTP_evidence"}
        compare(old, history, "inchikey", fields, numeric, "historical_lrtp_values")
        old_merged = _read_csv(artifacts["compound_inventory_with_qsar_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        compare(old_merged, history, "inchikey", fields, numeric, "historical_merged_values")
        old_audit = _read_csv(artifacts["lrtp_input_audit_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        audit_fields = [c for c in old_audit if c.startswith("LRTP_")]
        compare(old_audit, history, "inchikey", {c: c for c in audit_fields}, numeric, "historical_input_audit")
        old_index, history_index = old.set_index("inchikey"), history.set_index("inchikey")
        for key in old_index.index:
            differences.extend(_compare_evidence(old_index.at[key, "LRTP_evidence"], history_index.at[key, "LRTP_evidence"], key))
        checks.append({"scope": "historical_evidence_including_emission_scenarios", "rows": len(old), "fields": 1})
        compare(source, history, "inchikey", {c: c for c in ("qsar_inchikey", "vega_row_no", "qsar_identity_status",
                "qsar_identity_verified", "qsar_identity_reason")}, set(), "historical_identity_provenance")
        if not history["result_role"].eq("historical_reproduction_only").all():
            raise ValueError("Historical outputs must explicitly identify their audit-only role.")
        compare(source, analysis, "inchikey", {c: c for c in source if c != "inchikey"}, set(), "upstream_qsar_preservation")
        if "LRTP_evidence" in analysis or any("score" in c.lower() for c in analysis if c not in source):
            raise ValueError("Analysis output contains historical nested results or downstream scores.")
        aligned = analysis.set_index("inchikey").loc[history_index.index]
        expected_available = (aligned["qsar_identity_verified"].eq("True") & history_index["LRTP_input_status"].isin(["ok", "warning"]))
        if not aligned["lrtp_available"].eq(expected_available.map(str)).all():
            raise ValueError("Analysis availability does not enforce both identity and calculation status.")
        if not aligned["calculation_status"].equals(history_index["LRTP_input_status"]):
            raise ValueError("Historical calculation status was changed in the analysis projection.")
        review = aligned["qsar_identity_status"].eq("review_required")
        verified = aligned["qsar_identity_verified"].eq("True")
        expected_reason = pd.Series("", index=aligned.index)
        expected_reason.loc[~history_index["LRTP_input_status"].isin(["ok", "warning"])] = "calculation_" + history_index["LRTP_input_status"]
        expected_reason.loc[~verified] = "no_verified_report_association"
        expected_reason.loc[review] = "identity_review_required"
        if not expected_reason.equals(aligned["lrtp_exclusion_reason"]):
            raise ValueError("Analysis exclusion reasons differ from the declared policy.")
        expected = history_index.drop(columns="LRTP_evidence").copy()
        expected.loc[~expected_available, VALUE_COLUMNS] = ""
        expected.loc[review, "LRTP_input_status"] = "identity_review_required"
        compare(expected.reset_index(), analysis, "inchikey", fields, numeric, "analysis_identity_isolation")
        isolation = _read_csv(results / "identity_isolation_audit.csv")
        expected_pairs = {(k, f) for k in aligned.index[review] for f in VALUE_COLUMNS}
        if len(isolation) != len(expected_pairs) or set(zip(isolation["inchikey"], isolation["field"])) != expected_pairs:
            raise ValueError("Isolation audit does not enumerate every withheld field for every review identity.")
        for row in isolation.to_dict("records"):
            key, field = row["inchikey"], row["field"]
            if (row["historical_value"] != history_index.at[key, field] or row["analysis_value"] != "" or
                    row["exclusion_reason"] != "identity_review_required" or
                    row["identity_reason"] != aligned.at[key, "qsar_identity_reason"]):
                raise ValueError("Isolation audit values or reasons do not match the result tables.")
        input_audit = _read_csv(results / "lrtp_input_audit.csv")
        compare(analysis, input_audit, "inchikey", {c: c for c in ("calculation_status", "qsar_identity_status",
                "qsar_identity_reason", "lrtp_available", "lrtp_exclusion_reason")}, set(), "input_audit_statuses")
        compare(source, input_audit, "inchikey", {c: c for c in LRTP_REQUIRED_PREDICTION_COLUMNS}, set(), "raw_input_properties")
        input_fields = {"log_kaw": "log_kaw", "log_kow": "log_kow", "hl_air_h": "hl_air_h", "hl_water_h": "hl_water_h", "hl_soil_h": "hl_soil_h"}
        expected_inputs = []
        for row in old.to_dict("records"):
            evidence = json.loads(row["LRTP_evidence"])
            expected_inputs.append({"inchikey": row["inchikey"], **{k: "" if v is None else str(v) for k,v in evidence["inputs"].items()}})
        compare(pd.DataFrame(expected_inputs), input_audit, "inchikey", input_fields, set(input_fields), "converted_inputs_including_unavailable_rows")
        for name, key in (("identity_anomaly_sources.csv", "record_id"), ("identity_anomaly_reports.csv", "link_id")):
            before, after = _read_csv(upstream / name), _read_csv(results / name)
            if key == "link_id":
                for frame in (before, after):
                    frame[key] = frame["model_id"] + ":" + frame["vega_row_no"]
            compare(before, after, key, {c: c for c in before if c != key}, set(), name)
            if not after["lrtp_exclusion_reason"].eq("identity_review_required").all():
                raise ValueError("Anomaly provenance lost its LRTP exclusion reason.")
            lookup_key = "inchikey" if key == "record_id" else "qsar_inchikey"
            reasons = source.drop_duplicates(lookup_key).set_index(lookup_key)["qsar_identity_reason"]
            if not after[lookup_key].map(reasons).equals(after["identity_reason"]):
                raise ValueError("Anomaly provenance lost its chemical identity diagnostic.")
        counts = {"compounds": len(history), "historically_calculable": int(history["LRTP_input_status"].isin(["ok", "warning"]).sum()),
                  "available_after_identity_check": int(expected_available.sum()), "identity_excluded_compounds": int(review.sum()),
                  "identity_source_records": len(_read_csv(results / "identity_anomaly_sources.csv")),
                  "identity_report_links": len(_read_csv(results / "identity_anomaly_reports.csv"))}
        if manifest["counts"] != counts:
            raise ValueError("Manifest counts differ from validated outputs.")
        summary = {"status": "passed" if not differences else "failed", "scope": "Stage 3B; no downstream scoring",
                   "baseline_run": run["run_id"], "upstream_regression": "passed", **counts,
                   "historical_fields_compared": len(LRTP_OUTPUT_COLUMNS), "isolation_fields_audited": len(isolation),
                   "historical_status_counts": history["LRTP_input_status"].value_counts().to_dict(),
                   "numeric_comparison": "Exact decimal equality; no floating-point tolerance; recursive JSON evidence comparison",
                   "implementation_sha256": _file_hash(Path(__file__)), "lrtp_manifest_sha256": _file_hash(results / "lrtp_manifest.json"),
                   "scientific_identity_review": "pending", "independent_official_tool_validation": "not performed",
                   "interpretation": "Historical numerical agreement and intentional identity isolation are validated separately."}
    except (ValueError, KeyError, OSError) as exc:
        summary = {"status": "failed", "scope": "Stage 3B", "error": str(exc)}
    summary["unexplained_differences"] = len(differences)
    pd.DataFrame(differences, columns=["scope", "key", "field", "expected", "actual"]).to_csv(output_dir / "lrtp_validation_differences.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(checks, columns=["scope", "rows", "fields"]).to_csv(output_dir / "lrtp_validation_checks.csv", index=False, encoding="utf-8", lineterminator="\n")
    (output_dir / "lrtp_validation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _canonical_json_value(value):
    """Canonical semantic values: retain types and list order, equate decimal spellings."""
    if isinstance(value, dict):
        return ["object", [[k, _canonical_json_value(v)] for k, v in sorted(value.items())]]
    if isinstance(value, list): return ["array", [_canonical_json_value(v) for v in value]]
    if isinstance(value, bool) or value is None or isinstance(value, str): return [type(value).__name__, value]
    return ["number", str(Decimal(str(value)).normalize())]


def _semantic_digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(_canonical_json_value(value), separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _basic_historical_projection(payload, literature):
    """Recover the 4A boundary from archived final Stage 4 plus its pre-enrichment audit."""
    payload = json.loads(json.dumps(payload))
    for field in ("litchemplast_resolution", "fcchumon_resolution", "analytical_detectability"):
        payload.pop(field, None)
    block = payload["exposure"]["literature"]
    block.pop("litchemplast_count", None)
    if literature: block["litchemplast_count"] = literature
    return payload


def compare_basic_evidence(baseline, results, output_dir, upstream_results=None):
    """Validate only the basic extraction boundary and prediction-isolation policy."""
    from .evidence import DEFAULT_FIELDS, HISTORICAL_EVENT_FIELDS
    from .lrtp import VALUE_COLUMNS
    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    lrtp = Path(upstream_results) if upstream_results is not None else results.parent / "stage3" / "lrtp"
    stage2 = lrtp.parent.parent / "stage2"
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks = [], []
    def compare(old, new, fields, numeric, scope):
        differences.extend(_compare_qsar_frame(old, new, "inchikey", fields, numeric, scope))
        checks.append({"scope": scope, "rows": len(old), "fields": len(fields)})
    try:
        upstream = compare_lrtp(baseline, lrtp, output_dir / "stage3b")
        if upstream["status"] != "passed": raise ValueError("Upstream Stage 3B regression failed.")
        m = _read_json(results / "evidence_manifest.json")
        _verify_hash(DEFAULT_FIELDS, m["config_sha256"])
        _verify_hash(Path(__file__).with_name("evidence.py"), m["implementation_sha256"])
        _verify_hash(Path(__file__).with_name("_evidence_rules.py"), m["rules_sha256"])
        for name, folder, file in (("identity", stage2, "identity_manifest.json"), ("lrtp", lrtp, "lrtp_manifest.json"),
                                   ("qsar", lrtp.parent, "qsar_manifest.json")):
            _verify_hash(folder / file, m["upstream_manifests_sha256"][name])
        for name, digest in m["output_sha256"].items(): _verify_hash(results / name, digest)
        run = _read_json(baseline / "run_manifest.json")
        entry = run["stages"]["4"]
        _verify_hash(baseline / entry["checkpoint"], entry["checkpoint_sha256"])
        cp = _read_json(baseline / entry["checkpoint"])
        artifacts = {}
        for item in cp["artifacts"]:
            path = baseline / item["path"]
            _verify_hash(path, item["sha256"]); artifacts[item["artifact_id"]] = path
        baseline_inputs = {r["filename"]: r["sha256"] for r in _read_json(baseline / "input_manifest.json")["records"]}
        for source in m["inputs"]:
            if source["source_sha256"] != baseline_inputs[source["source_filename"]]: raise ValueError("Evidence source differs from frozen inputs.")
        prior = _read_csv(lrtp / "compound_lrtp.csv")
        analysis = _read_csv(results / "compound_evidence.csv")
        history = _read_csv(results / "basic_evidence_historical.csv")
        fields = ["db_extract_info", "classification_info_json", "classification_summary", "function_top_classes",
                  "polymer_context_summary", "structural_group_summary", "concern_status"]
        old = pd.read_csv(artifacts["compound_inventory_with_evidence_csv"], dtype=str, keep_default_na=False,
                          encoding="utf-8", usecols=["Inchikey_std", *fields]).rename(columns={"Inchikey_std": "inchikey"})
        plain = {c: c for c in fields if c not in {"db_extract_info", "classification_info_json"}}
        compare(old, history, plain, set(), "classification_summary_fields")
        expected_events, actual_events, literature = Counter(), Counter(), {}
        old_count = mismatch_count = 0
        with artifacts["compound_evidence_audit_jsonl"].open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line);old_count += 1;mismatch_count += event["status"] == "mismatch"
                expected_events[_semantic_digest(event)] += 1
                if event["status"] == "extracted" and event["field_path"] == "exposure.literature.litchemplast_count":
                    block = literature.setdefault(event["compound_key"], {}).setdefault(event["db"], [])
                    value = float(event["raw_value"])
                    if value not in block: block.append(value)
        originals = _read_csv(stage2 / "resolved_records.csv").set_index("record_id")
        original_ids = set(originals.index)
        actual_count = 0
        with (results / "basic_evidence_audit.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                e = json.loads(line);actual_count += 1
                event = {k: v for k, v in e.items() if k in HISTORICAL_EVENT_FIELDS}
                actual_events[_semantic_digest(event)] += 1
                r = originals.loc[e["source_record_id"]]
                if e["source_sha256"] != r["source_sha256"] or int(r["source_record_number"]) != int(e["row_index"]) + 1:
                    raise ValueError("Field audit lost its original source-row provenance.")
                if not e["query_record_ids"] or not set(e["query_record_ids"]) <= original_ids:
                    raise ValueError("Field audit has missing query-record provenance.")
                if e["status"] == "mismatch" and e["selection_reason"] != "excluded_identity_mismatch":
                    raise ValueError("Mismatch exclusion reason was not preserved.")
        for digest in sorted(set(expected_events) | set(actual_events)):
            if expected_events[digest] != actual_events[digest]:
                differences.append({"scope": "basic_field_audit", "key": digest, "field": "event_multiplicity",
                                    "expected": expected_events[digest], "actual": actual_events[digest]})
        checks.append({"scope": "every_historical_field_audit_event_with_multiplicity", "rows": old_count, "fields": len(HISTORICAL_EVENT_FIELDS)})
        historic = history.set_index("inchikey")
        for row in old.to_dict("records"):
            key = row["inchikey"]
            expected = _basic_historical_projection(json.loads(row["db_extract_info"]), literature.get(key, {}))
            for field, value in (("db_extract_info", expected), ("classification_info_json", json.loads(row["classification_info_json"]) if row["classification_info_json"] else None)):
                actual = json.loads(historic.at[key, field]) if historic.at[key, field] else None
                for diff in _compare_evidence(json.dumps(value), json.dumps(actual), key):
                    diff.update(scope="basic_evidence_values", field=diff["field"].replace("LRTP_evidence", field, 1));differences.append(diff)
        checks.append({"scope": "basic_JSON_values_pre_specialist_enrichment", "rows": len(old), "fields": 2})
        compare(history, analysis, {c:c for c in fields}, set(), "basic_evidence_retained_in_analysis")
        qsar_config = _read_json(Path(__file__).with_name("qsar_models.json"))
        prediction_fields = [c for c in qsar_config["legacy_merge_columns"] if not c.startswith("Basic | ")]
        expected = prior.copy();review = expected["qsar_identity_status"].eq("review_required")
        expected.loc[review, prediction_fields] = ""
        compare(expected, analysis, {c:c for c in prior if c != "inchikey"}, set(), "upstream_preservation_and_prediction_isolation")
        if not analysis["qsar_evidence_available"].equals(prior["qsar_identity_verified"]):
            raise ValueError("QSAR availability lost the upstream identity gate.")
        for forbidden in ("litchemplast_resolution", "fcchumon_resolution", "analytical_detectability"):
            if any(forbidden in json.loads(v) for v in history["db_extract_info"]): raise ValueError("Out-of-scope specialist evidence was generated.")
        if any(c.startswith("GIC_") or c in {"Analytical_detectability", "LRTP_evidence"} for c in analysis):
            raise ValueError("Out-of-scope or historical unverified evidence entered the analysis output.")
        isolation = _read_csv(results / "prediction_isolation_audit.csv")
        review_keys = set(prior.loc[review, "inchikey"])
        expected_pairs = {(k,f) for k in review_keys for f in [*prediction_fields,*VALUE_COLUMNS]}
        if len(isolation) != len(expected_pairs) or set(zip(isolation["inchikey"],isolation["field"])) != expected_pairs:
            raise ValueError("Prediction isolation audit is incomplete or duplicated.")
        pindex, aindex = prior.set_index("inchikey"), analysis.set_index("inchikey")
        for e in isolation.to_dict("records"):
            k,f = e["inchikey"],e["field"]
            if e["upstream_value"] != pindex.at[k,f] or e["analysis_value"] != "" or aindex.at[k,f] != "" or e["exclusion_reason"] != "identity_review_required":
                raise ValueError("Isolation values or reasons disagree with the result tables.")
        members = _read_csv(stage2 / "compound_memberships.csv")
        attempts, attempt_ids = [], set()
        with (results / "evidence_match_attempts.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                e=json.loads(line);attempts.append(e);attempt_ids.add(e["attempt_id"])
        if Counter((e["compound_key"],e["query_record_id"]) for e in attempts) != Counter(zip(members["inchikey"],members["record_id"])):
            raise ValueError("Not all source-member attempts were preserved.")
        required_rows = set(members["record_id"]);candidate_count = 0
        candidate_pairs = Counter()
        with (results / "evidence_candidates.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                e=json.loads(line);candidate_count+=1;required_rows.add(e["record_id"])
                if e["attempt_id"] not in attempt_ids: raise ValueError("Candidate has no source-member attempt.")
                candidate_pairs[e["attempt_id"]]+=1
                reason = "first_matching_source_row" if e["selected_for_identity_check"] else "not_selected_first_row_policy"
                if e["selection_reason"] != reason: raise ValueError("Candidate selection/exclusion reason is missing.")
        if any(candidate_pairs[e["attempt_id"]] != e["hit_count"] for e in attempts): raise ValueError("Candidate multiplicities do not match search hits.")
        source_ids=set()
        with (results / "evidence_source_rows.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                e=json.loads(line);rid=e["record_id"]
                if rid in source_ids: raise ValueError("Duplicated retained source rows.")
                source_ids.add(rid)
                for field in ("source_sha256","source_filename","table_id","source_record_number","source_native_id","reported_fields_json"):
                    if e[field] != originals.at[rid,field]: raise ValueError("Retained source provenance changed.")
                if not isinstance(e["raw_fields"],dict): raise ValueError("Missing complete raw source row.")
        if source_ids != required_rows: raise ValueError("Retained rows do not cover all queries and candidates.")
        decision_count = 0
        selected_decisions = set()
        with (results / "classification_selection_audit.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                e = json.loads(line); decision_count += 1
                if e["source_record_id"] not in source_ids or e["source_sha256"] != originals.at[e["source_record_id"], "source_sha256"]:
                    raise ValueError("Classification decision lost source provenance.")
                if e["selected"]:
                    pair = (e["compound_key"], e["field_path"])
                    if pair in selected_decisions: raise ValueError("More than one last-row classification value was selected.")
                    selected_decisions.add(pair)
                    value = json.loads(historic.at[e["compound_key"], "db_extract_info"])
                    for part in e["field_path"].split("."): value = value[part]
                    if _semantic_digest(value) != _semantic_digest(e["normalized_value"]):
                        raise ValueError("Selected classification value differs from the result.")
                if e["selection_reason"] not in {"selected_last_valid_row", "superseded_by_later_valid_row", "excluded_identity_mismatch", "missing_source_value", "invalid_numeric_value", "not_selected_nonpositive_list_annotation", "omitted_all_zero_block_historical_rule"}:
                    raise ValueError("Missing classification selection or exclusion reason.")
        counts={"compounds":len(history),"source_member_attempts":len(attempts),"matched_candidates":candidate_count,
                "retained_source_rows":len(source_ids),"historical_audit_events":actual_count,"identity_mismatch_events":mismatch_count,
                "identity_review_compounds":len(review_keys),"isolated_prediction_fields":len(isolation),"classification_decisions":decision_count}
        if m["counts"] != counts: raise ValueError("Evidence manifest counts differ from validated artifacts.")
        summary={"status":"passed" if not differences else "failed","scope":"Stage 4A only; no 4B/4C or downstream scoring",
                 "baseline_run":run["run_id"],"upstream_regression":"passed",**counts,
                 "baseline_boundary":"Final Stage 4 with only the three specialist blocks removed and generic literature counts restored from the frozen basic audit",
                 "numeric_comparison":"Exact decimal values and recursive JSON comparison; audit multiplicity retained",
                 "implementation_sha256":_file_hash(Path(__file__)),"evidence_manifest_sha256":_file_hash(results/'evidence_manifest.json'),
                 "scientific_identity_review":"pending","interpretation":"Historical basic evidence reproduction does not independently establish source correctness; prediction isolation is checked separately."}
    except (ValueError,KeyError,OSError) as exc:
        summary={"status":"failed","scope":"Stage 4A","error":str(exc)}
    summary['unexplained_differences']=len(differences)
    pd.DataFrame(differences,columns=['scope','key','field','expected','actual']).to_csv(output_dir/'evidence_validation_differences.csv',index=False,encoding='utf-8',lineterminator='\n')
    pd.DataFrame(checks,columns=['scope','rows','fields']).to_csv(output_dir/'evidence_validation_checks.csv',index=False,encoding='utf-8',lineterminator='\n')
    (output_dir/'evidence_validation_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return summary


def compare_specialist_evidence(baseline, results, output_dir, upstream_results=None):
    """Compare the complete 4B boundary and separately verify model-identity isolation."""
    from .evidence_specialists import DEFAULT_POLICY
    from .lrtp import VALUE_COLUMNS
    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    basic = Path(upstream_results) if upstream_results is not None else results.parent
    stage2 = basic.parent / "stage2"
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks = [], []

    def compare(old, new, fields, scope):
        differences.extend(_compare_qsar_frame(old, new, "inchikey", {c: c for c in fields}, set(), scope))
        checks.append({"scope": scope, "rows": len(old), "fields": len(fields)})

    def compare_json(old, new, key, scope):
        for diff in _compare_evidence(json.dumps(old), json.dumps(new), key):
            diff.update(scope=scope, field=diff["field"].replace("LRTP_evidence", scope, 1))
            differences.append(diff)

    def jsonl(path):
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    try:
        upstream = compare_basic_evidence(baseline, basic, output_dir / "stage4a")
        if upstream["status"] != "passed":
            raise ValueError("Upstream Stage 4A regression failed.")
        manifest = _read_json(results / "specialist_manifest.json")
        _verify_hash(DEFAULT_POLICY, manifest["policy_sha256"])
        _verify_hash(Path(__file__).with_name("evidence_specialists.py"), manifest["implementation_sha256"])
        _verify_hash(stage2 / "identity_manifest.json", manifest["upstream_manifest_sha256"]["identity"])
        _verify_hash(basic / "evidence_manifest.json", manifest["upstream_manifest_sha256"]["basic"])
        for file, digest in manifest["output_sha256"].items():
            _verify_hash(results / file, digest)
        run = _read_json(baseline / "run_manifest.json")
        artifacts = {}
        for stage in ("3", "4"):
            entry = run["stages"][stage]
            _verify_hash(baseline / entry["checkpoint"], entry["checkpoint_sha256"])
            for item in _read_json(baseline / entry["checkpoint"])["artifacts"]:
                path = baseline / item["path"]
                _verify_hash(path, item["sha256"])
                artifacts[item["artifact_id"]] = path
        frozen_inputs = {r["filename"]: r["sha256"] for r in _read_json(baseline / "input_manifest.json")["records"]}
        for item in manifest["inputs"]:
            if item["sha256"] != frozen_inputs[item["filename"]]:
                raise ValueError("Specialist source differs from frozen inputs.")
        old = _read_csv(artifacts["compound_inventory_with_evidence_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        before = _read_csv(artifacts["compound_inventory_with_qsar_csv"]).rename(columns={"Inchikey_std": "inchikey"})
        history = _read_csv(results / "specialist_historical.csv")
        analysis = _read_csv(results / "compound_specialist_evidence.csv")
        prior = _read_csv(basic / "compound_evidence.csv")
        cas = _read_csv(results / "cas_identity_view.csv")
        compare(old, history, ["db_LitChemPlast"], "historical_membership_projection")
        compare(before, cas, ["CAS", "cas_mapping_status", "cas_mapping_count", "cas_connectivity_count"], "compound_CAS_projection")
        old_index = before.set_index("inchikey")
        for row in cas.to_dict("records"):
            for field in ("cas_values_json", "cas_mapping_details_json"):
                compare_json(json.loads(old_index.at[row["inchikey"], field]), json.loads(row[field]), row["inchikey"], field)
        checks.append({"scope": "all_CAS_aliases_and_mapping_details", "rows": len(cas), "fields": 2})
        hindex = history.set_index("inchikey")
        for row in old.to_dict("records"):
            payload = json.loads(row["db_extract_info"])
            payload.pop("analytical_detectability", None)
            compare_json(payload, json.loads(hindex.at[row["inchikey"], "db_extract_info"]), row["inchikey"], "complete_4B_evidence_JSON")
        checks.append({"scope": "complete_4B_evidence_JSON", "rows": len(old), "fields": 1})
        audits = {}
        for name, legacy in (("litchemplast", "litchemplast_resolution_audit_jsonl"),
                             ("fcchumon", "fcchumon_detection_resolution_audit_jsonl")):
            expected = jsonl(artifacts[legacy])
            actual = jsonl(results / (name + "_resolution_audit.jsonl"))
            if len(actual) != len(expected) or len({r["compound_key"] for r in actual}) != len(actual):
                raise ValueError("Specialist audit rows are missing or duplicated.")
            mapping = {r["compound_key"]: r for r in actual}
            for row in expected:
                compare_json(row, mapping[row["compound_key"]], row["compound_key"], name + "_resolution")
            audits[name] = mapping
            checks.append({"scope": name + "_resolution_every_field", "rows": len(expected), "fields": len(expected[0])})
        compare(prior, analysis, [c for c in prior if c not in {"inchikey", "db_extract_info"}], "unchanged_upstream_fields_and_prediction_isolation")
        compare(history, analysis, ["db_extract_info"], "historical_evidence_retained_in_analysis")
        for row in analysis.to_dict("records"):
            lit, human = (audits[name][row["inchikey"]] for name in ("litchemplast", "fcchumon"))
            state = ("detected" if human["detected"] else "matched_without_positive_count") if human["selected"] else human["match_method"]
            expected = {"litchemplast_evidence_available": str(lit["selected"]), "litchemplast_match_method": lit["match_method"],
                        "fcchumon_evidence_available": str(human["selected"]), "fcchumon_evidence_status": state,
                        "fcchumon_detected": str(human["detected"]) if human["selected"] else ""}
            if any(row[k] != value for k, value in expected.items()):
                raise ValueError("Analysis availability conflates missing, rejected or matched evidence.")
        if any(c.startswith("GIC_") or c in {"Analytical_detectability", "LRTP_evidence", "db_LitChemPlast"} for c in analysis):
            raise ValueError("Out-of-scope or historical-only fields entered analysis.")
        if any("analytical_detectability" in json.loads(v) for v in history["db_extract_info"]):
            raise ValueError("Stage 4C evidence was generated.")
        review = analysis["qsar_identity_status"].eq("review_required")
        predictions = [c for c in _read_json(Path(__file__).with_name("qsar_models.json"))["legacy_merge_columns"] if not c.startswith("Basic | ")]
        if analysis.loc[review, predictions + VALUE_COLUMNS].ne("").any().any():
            raise ValueError("An identity-review prediction is available in Stage 4B.")
        exceptions = _read_csv(results / "identity_review_evidence.csv")
        if exceptions["inchikey"].duplicated().any() or set(exceptions["inchikey"]) != set(analysis.loc[review, "inchikey"]):
            raise ValueError("Identity-review subset is incomplete.")
        aindex = analysis.set_index("inchikey")
        for row in exceptions.to_dict("records"):
            key = row["inchikey"]
            for col in ("qsar_inchikey", "vega_row_no", "litchemplast_evidence_available", "litchemplast_match_method", "fcchumon_evidence_available", "fcchumon_evidence_status", "fcchumon_detected"):
                if row[col] != aindex.at[key, col]:
                    raise ValueError("Identity-review subset differs from the analysis output.")
            lit = audits["litchemplast"][key]
            for field, value in (("litchemplast_linked_record_count", lit["linked_record_count"]),
                                 ("litchemplast_unique_publication_count", lit["unique_publication_count"])):
                actual = row[field]
                if (value is None and actual != "") or (value is not None and (actual == "" or Decimal(actual) != Decimal(value))):
                    raise ValueError("Identity-review literature counts differ from the full audit.")
            if row["identity_reason"] != aindex.at[key, "qsar_identity_reason"] or row["prediction_exclusion_reason"] != "identity_review_required":
                raise ValueError("Identity-review exclusion reasons changed.")
        sources = jsonl(results / "specialist_source_rows.jsonl")
        source_map = {r["record_id"]: r for r in sources}
        if len(source_map) != len(sources):
            raise ValueError("Duplicated source record identifiers.")
        originals = _read_csv(stage2 / "resolved_records.csv").set_index("record_id")
        source_meta = {r["table_id"]: r for r in manifest["inputs"]}
        for table_id, meta in source_meta.items():
            source = [r for r in sources if r["table_id"] == table_id]
            if [r["source_record_number"] for r in source] != list(range(1, meta["rows"] + 1)):
                raise ValueError("Source rows are incomplete or reordered.")
        for row in sources:
            meta = source_meta[row["table_id"]]
            if row["source_sha256"] != meta["sha256"] or row["source_row_number"] != row["source_record_number"] + meta["header"] + 1:
                raise ValueError("Source hash or row location changed.")
            if row["table_id"] != "litchemplast_links":
                for col in ("source_sha256", "table_id", "source_native_id"):
                    if row[col] != originals.at[row["record_id"], col]:
                        raise ValueError("Source provenance differs from Stage 2.")
        cas_links = _read_csv(results / "cas_source_links.csv")
        members = _read_csv(stage2 / "compound_memberships.csv")
        if set(zip(cas_links["inchikey"], cas_links["record_id"])) != set(zip(members["inchikey"], members["record_id"])):
            raise ValueError("CAS provenance lost source members.")
        for row in cas_links.to_dict("records"):
            original = originals.loc[row["record_id"]]
            if row["cas_reported"] != original["cas_reported"] or row["source_sha256"] != original["source_sha256"]:
                raise ValueError("CAS alias provenance differs from Stage 2.")
        conversions = jsonl(results / "count_conversion_audit.jsonl")
        conversion_map = {(r["record_id"], r["source_column"]): r for r in conversions}
        if len(conversion_map) != len(conversions):
            raise ValueError("Duplicated count-conversion decisions.")
        candidates = jsonl(results / "specialist_candidates.jsonl")
        selected_counts = {"litchemplast": Counter(), "fcchumon": Counter()}
        selected_source_rows = defaultdict(set)
        selected_link_rows = defaultdict(set)
        for row in candidates:
            kind = "litchemplast" if row["candidate_type"].startswith("lit_") else "fcchumon"
            key = row["compound_key"]
            if not row["source_record_ids"] or any(r not in source_map for r in row["source_record_ids"] + row["relationship_record_ids"]):
                raise ValueError("Candidate source links are missing.")
            if not row["selection_reason"]:
                raise ValueError("Candidate has no selection or exclusion reason.")
            if row["selected"]:
                selected_counts[kind][key] += 1
                selected_source_rows[key, kind].update(row["source_record_ids"])
                selected_link_rows[key].update(row["relationship_record_ids"])
            if kind == "fcchumon" and row["selected"]:
                chosen = defaultdict(list)
                for field in row["field_decisions"]:
                    conversion = conversion_map[field["record_id"], field["source_column"]]
                    values = [conversion_map[rid, field["source_column"]]["normalized_value"] for rid in row["source_record_ids"]]
                    if field["record_id"] not in row["source_record_ids"] or field["normalized_value"] != conversion["normalized_value"]:
                        raise ValueError("Maximum-count decision differs from its source conversion.")
                    expected_selection = field["normalized_value"] == max(values)
                    reason = "supports_group_maximum" if expected_selection else "not_selected_lower_count"
                    if field["selected_for_maximum"] != expected_selection or field["selection_reason"] != reason:
                        raise ValueError("Maximum-count selection or exclusion reason is incorrect.")
                    if field["selected_for_maximum"]:
                        chosen[field["source_column"]].append(field["normalized_value"])
                resolution = audits[kind][key]
                expected = resolution["detection_count"]
                if not chosen[resolution["detection_field"]] or set(chosen[resolution["detection_field"]]) != {expected}:
                    raise ValueError("Human detection count lost its contributing source rows.")
        for kind, records in audits.items():
            if any(selected_counts[kind][key] != int(r["selected"]) for key, r in records.items()):
                raise ValueError("Selected evidence lacks a unique traced candidate group.")
        link_decisions = jsonl(results / "literature_link_decisions.jsonl")
        link_count, publication_count, actual_link_rows = Counter(), Counter(), defaultdict(set)
        counted_links, counted_publications = defaultdict(set), defaultdict(set)
        for row in link_decisions:
            key, rid = row["compound_key"], row["record_id"]
            raw = source_map[rid]["raw_fields"]
            if rid in actual_link_rows[key] or rid not in selected_link_rows[key]:
                raise ValueError("Relationship decision is duplicated or has no selected source group.")
            actual_link_rows[key].add(rid)
            if any(row[f] != raw[f] for f in ("Chem_id", "LitChem_id", "Lit_id")):
                raise ValueError("Relationship identifiers differ from the retained source row.")
            if not row["chemical_record_ids"] or not set(row["chemical_record_ids"]) <= selected_source_rows[key, "litchemplast"]:
                raise ValueError("Relationship lost its selected Chemical source row.")
            for identifier, flag, reason_field, seen in (("LitChem_id", "counted_link_record", "link_reason", counted_links),
                                                         ("Lit_id", "counted_publication", "publication_reason", counted_publications)):
                value = row[identifier]
                expected_flag = value is not None and value not in seen[key]
                reason = "missing_identifier" if value is None else "counted_unique_identifier" if expected_flag else "duplicate_identifier_not_recounted"
                if row[flag] != expected_flag or row[reason_field] != reason:
                    raise ValueError("Unique/duplicate relationship-count decision is incorrect.")
                seen[key].add(value)
            link_count[key] += row["counted_link_record"]
            publication_count[key] += row["counted_publication"]
        for key, row in audits["litchemplast"].items():
            if row["selected"] and (link_count[key] != row["linked_record_count"] or publication_count[key] != row["unique_publication_count"] or actual_link_rows[key] != selected_link_rows[key]):
                raise ValueError("Unique relationship counts differ from source contribution decisions.")
        for row in conversions:
            if row["raw_value"] != source_map[row["record_id"]]["raw_fields"][row["source_column"]] or not row["conversion_reason"]:
                raise ValueError("Count conversion lost its raw value or reason.")
        counts = {"compounds": len(analysis), "source_rows": len(sources), "cas_source_links": len(cas_links),
                  "candidate_groups": len(candidates), "literature_link_decisions": len(link_decisions), "count_conversions": len(conversions),
                  "identity_review_compounds": len(exceptions), "litchemplast_selected": sum(r["selected"] for r in audits["litchemplast"].values()),
                  "fcchumon_selected": sum(r["selected"] for r in audits["fcchumon"].values()),
                  "fcchumon_detected": sum(r["detected"] for r in audits["fcchumon"].values())}
        if manifest["counts"] != counts:
            raise ValueError("Manifest counts disagree with validated artifacts.")
        changes = int(before["db_LitChemPlast"].ne(old["db_LitChemPlast"]).sum())
        summary = {"status": "passed" if not differences else "failed", "scope": "Stage 4B only; no 4C or downstream scoring",
                   "baseline_run": run["run_id"], "upstream_regression": "passed", **counts,
                   "historical_membership_flag_changes": changes, "isolated_prediction_fields": int(review.sum()) * len(predictions + VALUE_COLUMNS),
                   "comparison_policy": "Exact text, scalar types and decimal values; recursive JSON and list order; no numerical tolerance",
                   "baseline_boundary": "Final Stage 4 without analytical_detectability JSON and GIC top-level columns",
                   "implementation_sha256": _file_hash(Path(__file__)), "specialist_manifest_sha256": _file_hash(results / "specialist_manifest.json"),
                   "scientific_identity_review": "pending", "interpretation": "Historical agreement and inherited prediction isolation verified separately; no independent scientific identity confirmation."}
    except (ValueError, KeyError, OSError) as exc:
        summary = {"status": "failed", "scope": "Stage 4B", "error": str(exc)}
    summary["unexplained_differences"] = len(differences)
    pd.DataFrame(differences, columns=["scope", "key", "field", "expected", "actual"]).to_csv(output_dir / "specialist_validation_differences.csv", index=False, encoding="utf-8", lineterminator="\n")
    pd.DataFrame(checks, columns=["scope", "rows", "fields"]).to_csv(output_dir / "specialist_validation_checks.csv", index=False, encoding="utf-8", lineterminator="\n")
    (output_dir / "specialist_validation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def compare_annotations(baseline, results, output_dir, upstream_results=None):
    """Check the complete historical Stage 4 boundary, provenance and isolated analysis view."""
    from .evidence_annotations import DEFAULT_POLICY, OUTPUT_COLUMNS, dependency_fingerprint
    from .evidence_specialists import require_prediction_isolation
    from .lrtp import _verify_outputs
    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    upstream_folder = Path(upstream_results) if upstream_results is not None else results.parent / '4b'
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks = [], []

    def jsonl(path):
        with path.open(encoding='utf-8') as stream:
            return [json.loads(line) for line in stream]

    def compare_json(a, b, key, scope):
        for diff in _compare_evidence(json.dumps(a), json.dumps(b), key):
            diff.update(scope=scope, field=diff['field'].replace('LRTP_evidence', scope, 1))
            differences.append(diff)

    def compare_frame(a, b, fields, numeric, scope):
        fields = [c for c in fields if c != 'inchikey']
        differences.extend(_compare_qsar_frame(a, b, 'inchikey', {c: c for c in fields}, set(numeric), scope))
        checks.append({'scope': scope, 'rows': len(a), 'fields': len(fields)})

    try:
        previous = compare_specialist_evidence(baseline, upstream_folder, output_dir / 'stage4b')
        if previous['status'] != 'passed': raise ValueError('Upstream Stage 4B regression failed.')
        manifest = _read_json(results / 'annotation_manifest.json')
        policy = _read_json(DEFAULT_POLICY)
        _verify_hash(DEFAULT_POLICY, manifest['policy_sha256'])
        _verify_hash(Path(__file__).with_name('evidence_annotations.py'), manifest['implementation_sha256'])
        _verify_hash(upstream_folder / 'specialist_manifest.json', manifest['upstream_manifest_sha256'])
        _verify_outputs(results, manifest)
        if dependency_fingerprint() != manifest['dependency']: raise ValueError('GIC dependency changed.')
        if manifest['inputs'] != policy['inputs']: raise ValueError('Input declarations differ from policy.')
        run = _read_json(baseline / 'run_manifest.json')
        frozen = {r['filename']: r['sha256'] for r in _read_json(baseline / 'input_manifest.json')['records']}
        for item in manifest['inputs']:
            if item['historical_hash_recorded'] and item['sha256'] != frozen[item['parts'][-1]]:
                raise ValueError('Annotation input differs from frozen run: ' + item['role'])
        checkpoint = baseline / run['stages']['4']['checkpoint']
        _verify_hash(checkpoint, run['stages']['4']['checkpoint_sha256'])
        artifacts = {}
        for record in _read_json(checkpoint)['artifacts']:
            path = baseline / record['path']
            _verify_hash(path, record['sha256'])
            artifacts[record['artifact_id']] = path
        old = _read_csv(artifacts['compound_inventory_with_evidence_csv']).rename(columns={'Inchikey_std': 'inchikey'})
        prior = _read_csv(upstream_folder / 'compound_specialist_evidence.csv')
        actual = _read_csv(results / 'compound_annotated_evidence.csv')
        history = _read_csv(results / 'annotation_historical.csv')
        numeric = ['GIC_regulatory_listing_count', 'GIC_inventory_listing_count']
        compare_frame(old, history, OUTPUT_COLUMNS, numeric, 'historical_annotation_fields')
        compare_frame(history, actual, OUTPUT_COLUMNS + ['db_extract_info'], numeric, 'historical_analysis_annotation_agreement')
        compare_frame(prior, actual, [c for c in prior.columns if c != 'db_extract_info'], [], 'unchanged_upstream_fields')
        old_map = old.set_index('inchikey')
        prior_map = prior.set_index('inchikey')
        for row in actual.to_dict('records'):
            key = row['inchikey']
            payload = json.loads(row['db_extract_info'])
            compare_json(json.loads(old_map.at[key, 'db_extract_info']), payload, key, 'complete_stage4_evidence_JSON')
            without_annotation = {k: v for k, v in payload.items() if k != 'analytical_detectability'}
            compare_json(json.loads(prior_map.at[key, 'db_extract_info']), without_annotation, key, 'upstream_evidence_preserved')
        checks.append({'scope': 'complete_stage4_evidence_JSON', 'rows': len(actual), 'fields': 1})
        expected_audit = jsonl(artifacts['gic_regulatory_audit_jsonl'])
        observed_audit = jsonl(results / 'gic_resolution_audit.jsonl')
        gic_map = {r['compound_key']: r for r in observed_audit}
        if len(gic_map) != len(actual) or len(observed_audit) != len(actual) or set(gic_map) != set(actual['inchikey']):
            raise ValueError('GIC audit keys are missing or duplicated.')
        excluded_runtime_fields = ['inventory_file', 'metadata_file', 'generated_at']
        runtime = []
        used_metadata = {}
        for row in expected_audit:
            key = row['compound_key']
            compare_json({k: v for k, v in row.items() if k not in excluded_runtime_fields}, gic_map[key], key, 'GIC_resolution')
            runtime.append({'compound_key': key, 'historical_runtime_fields': {k: row[k] for k in excluded_runtime_fields},
                            'current_policy': 'Fixed source parts and hashes are in annotation_manifest.json; output timestamps are omitted for deterministic replay.'})
            for listing in row['listings']:
                tag = listing['list_tag']
                if tag in used_metadata and used_metadata[tag] != listing:
                    raise ValueError('Frozen metadata is internally inconsistent.')
                used_metadata[tag] = listing
        checks.append({'scope': 'GIC_resolution', 'rows': len(observed_audit), 'fields': len(observed_audit[0])})
        metadata = {r['effective_listing']['list_tag']: r for r in jsonl(results / 'gic_metadata_audit.jsonl')}
        for tag, listing in used_metadata.items():
            compare_json(listing, metadata[tag]['effective_listing'], tag, 'frozen_used_metadata')
        checks.append({'scope': 'frozen_used_metadata', 'rows': len(used_metadata), 'fields': 11})
        candidates = jsonl(results / 'norman_candidates.jsonl')
        candidate_map = {r['record_id']: r for r in candidates}
        if len(candidate_map) != len(candidates): raise ValueError('Duplicated NORMAN source IDs.')
        selected = {r['lookup_inchikey']: r for r in candidates if r['selected']}
        if len(selected) != sum(r['selected'] for r in candidates): raise ValueError('More than one selected NORMAN row per key.')
        norman = jsonl(results / 'norman_resolution_audit.jsonl')
        if len(norman) != len(actual) or {r['compound_key'] for r in norman} != set(actual['inchikey']):
            raise ValueError('NORMAN audit identities differ.')
        analysis_map = actual.set_index('inchikey')
        for row in norman:
            key = row['compound_key']
            source = selected.get(key)
            if row['source_record_id'] != (source['record_id'] if source else None):
                raise ValueError('Selected NORMAN source link differs from ranking decision.')
            evidence = json.loads(analysis_map.at[key, 'db_extract_info']).get('analytical_detectability')
            if source:
                if evidence['norman_susdat_id'] != source['source_native_id'] or evidence['lookup_inchikey'] != key:
                    raise ValueError('NORMAN source identity was lost.')
            elif evidence is not None: raise ValueError('Unmatched NORMAN evidence was attached.')
            if analysis_map.at[key, 'norman_prediction_available'] != str(source is not None):
                raise ValueError('Incorrect NORMAN availability flag.')
        bridge_rows = {r['record_id']: r for r in jsonl(results / 'cid_bridge_source_rows.jsonl')}
        bridge_links = jsonl(results / 'cid_bridge_links.jsonl')
        from .evidence_annotations import _normalise_cid, _parse_cids, source_record
        inputs_by_name = {r['parts'][-1]: r['sha256'] for r in manifest['inputs']}
        for row in candidates + list(bridge_rows.values()):
            if row['source_sha256'] != inputs_by_name[row['source_filename']]:
                raise ValueError('Source-row hash differs from the pinned input.')
            source = {'id': row['source_id'], 'table_id': row['table_id'], 'sha256': row['source_sha256'],
                      'filename': row['source_filename'], 'sheet': row['source_sheet']}
            expected_record = source_record(source, row['source_record_number'], row['raw_fields'], row['source_native_id'])
            if expected_record != {k: row[k] for k in expected_record}:
                raise ValueError('Source-row identity or parsed/physical row provenance changed.')
        if any(not row['decision_reason'] for row in candidates):
            raise ValueError('NORMAN candidate selection or exclusion reason is missing.')
        for link in bridge_links:
            raw = bridge_rows[link['source_record_id']]['raw_fields']
            if str(raw[link['key_column']]).strip().upper() != link['compound_key']:
                raise ValueError('CID bridge lost its source key.')
            cids = _parse_cids(raw[link['cid_column']]) if link['source']=='pubchemlite' else {_normalise_cid(raw[link['cid_column']])} - {None}
            if link['cids'] != sorted(cids) or link['decision_reason'] != ('eligible_bridge' if cids else 'missing_or_unparseable_cid'):
                raise ValueError('CID bridge values or exclusion reasons differ from source fields.')
        source_sids = {r['sid']: r for r in jsonl(results / 'gic_source_rows.jsonl')}
        tag_map = manifest['gic_inventory_tag_dictionary']['list_data']
        identifier_sources = jsonl(results / 'gic_identifier_tag_sources.jsonl')
        identifier_tags = {}
        for source in identifier_sources:
            if source['list_tags'] != [tag_map[str(i)] for i in source['list_ids']]:
                raise ValueError('GIC identifier support tags differ from raw tag IDs.')
            identifier_tags.setdefault(source['identifier'], set()).update(source['list_tags'])
        for source in source_sids.values():
            local = {tag_map[str(i)] for values in source['raw_fields'].values() for ids in values.values() for i in ids}
            effective = set().union(*(identifier_tags[value] for value in source['effective_identifiers']))
            if source['local_list_tags'] != sorted(local) or source['effective_list_tags'] != sorted(effective) or source['shared_identifier_added_tags'] != sorted(effective - local):
                raise ValueError('GIC shared-identifier tag propagation lost its provenance.')
        used_sids = set()
        expected_decisions = 0
        for audit in observed_audit:
            key = audit['compound_key']
            for attempt in audit['lookup_attempts']:
                expected_decisions += 1
                tags = set()
                for sid in attempt['matched_sids']:
                    used_sids.add(sid)
                    tags.update(source_sids[sid]['effective_list_tags'])
                if sorted(tags) != attempt['matched_list_tags']: raise ValueError('GIC tags differ from the effective shared-identifier trace.')
            flags = {'gic_match_method': audit['match_method'], 'gic_name_review_required': str(audit['match_method']=='chemical_name'),
                     'gic_multiple_cids': str(len(audit['query_values']) > 1 if audit['match_method']=='cid_bridge' else False),
                     'gic_multiple_sids': str(len(audit['matched_sids']) > 1), 'gic_metadata_historical_hash_available': 'False',
                     'gic_shared_identifier_tag_expansion': str(bool(set(audit['matched_list_tags']) - set().union(*(set(source_sids[sid]['local_list_tags']) for sid in audit['matched_sids']))))}
            for field, expected in flags.items():
                if analysis_map.at[key, field] != expected: raise ValueError('Incorrect association review flag: ' + field)
        if set(source_sids) != used_sids: raise ValueError('GIC source ledger omits or adds SID records.')
        bridge_ids = {}
        for link in bridge_links:
            if link['cids']: bridge_ids.setdefault(link['compound_key'], set()).add(link['source_record_id'])
        decisions = jsonl(results / 'gic_match_decisions.jsonl')
        if len(decisions) != expected_decisions: raise ValueError('Query decisions are incomplete.')
        for decision in decisions:
            if not decision['decision_reason']: raise ValueError('Missing query decision reason.')
            local = set().union(*(set(source_sids[sid]['local_list_tags']) for sid in decision['matched_sids']))
            if decision['shared_identifier_added_tags'] != sorted(set(decision['matched_list_tags']) - local):
                raise ValueError('Query-level shared identifier expansion differs from source support.')
            if decision['selected'] != (decision['method'] == gic_map[decision['compound_key']]['match_method']):
                raise ValueError('Selected query path differs from historical resolution.')
            expected_ids = sorted(bridge_ids.get(decision['compound_key'], set())) if decision['method']=='cid_bridge' else []
            if decision['cid_source_record_ids'] != expected_ids: raise ValueError('CID query source links are incomplete or inconsistent.')
        require_prediction_isolation(actual)
        review = actual['qsar_identity_status'].eq('review_required')
        exceptions = _read_csv(results / 'identity_review_annotations.csv')
        compare_frame(actual.loc[review], exceptions, [c for c in exceptions.columns if c != 'prediction_exclusion_reason'], [], 'identity_review_annotations')
        if not exceptions['prediction_exclusion_reason'].eq('identity_review_required').all(): raise ValueError('Review reasons lost.')
        links = jsonl(results / 'identity_review_source_links.jsonl')
        members = _read_csv(results.parent.parent / 'stage2' / 'compound_memberships.csv')
        expected_links = members.loc[members['inchikey'].isin(exceptions['inchikey'])].to_dict('records')
        if Counter(_semantic_digest(x) for x in links) != Counter(_semantic_digest(x) for x in expected_links):
            raise ValueError('Identity-review source links changed.')
        counts = {'compounds': len(actual), 'norman_matched': sum(r['source_record_id'] is not None for r in norman),
                  'gic_matched': sum(r['regulatory_listing_count'] > 0 for r in observed_audit),
                  'gic_name_review_required': sum(r['match_method']=='chemical_name' for r in observed_audit),
                  'gic_tag_expansion_review_required': int(actual['gic_shared_identifier_tag_expansion'].eq('True').sum()),
                  'identity_review_compounds': len(exceptions), 'identity_review_source_links': len(links)}
        if counts != manifest['counts']: raise ValueError('Annotation counts differ from validated records.')
        with (output_dir / 'runtime_provenance_comparison.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
            for row in runtime: stream.write(json.dumps(row) + '\n')
        summary = {'status': 'passed' if not differences else 'failed', 'scope': 'Stage 4C; no downstream scoring',
                   'baseline_run': run['run_id'], 'upstream_regression': 'passed', **counts,
                   'gic_match_methods': manifest['gic_match_methods'], 'frozen_metadata_tags_checked': len(used_metadata),
                   'metadata_historical_byte_hash': 'unavailable; used effective fields compared to frozen audit',
                   'gic_historical_version': 'unrecorded; current legacy implementation matched by source fingerprint',
                   'excluded_runtime_fields': excluded_runtime_fields,
                   'comparison_policy': 'Exact text, types, decimal values, recursive JSON and list order; no numerical tolerance',
                   'isolated_prediction_fields': len(exceptions) * 69, 'scientific_identity_review': 'pending',
                   'annotation_manifest_sha256': _file_hash(results / 'annotation_manifest.json'),
                   'validation_implementation_sha256': _file_hash(Path(__file__))}
    except (ValueError, KeyError, OSError, ImportError) as exc:
        summary = {'status': 'failed', 'scope': 'Stage 4C', 'error': str(exc)}
    summary['unexplained_differences'] = len(differences)
    pd.DataFrame(differences, columns=['scope','key','field','expected','actual']).to_csv(output_dir / 'annotation_validation_differences.csv', index=False, encoding='utf-8', lineterminator='\n')
    pd.DataFrame(checks, columns=['scope','rows','fields']).to_csv(output_dir / 'annotation_validation_checks.csv', index=False, encoding='utf-8', lineterminator='\n')
    (output_dir / 'annotation_validation_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    return summary


def compare_pm_hazard(baseline, results, output_dir, upstream_results=None):
    """Validate P/M reproduction, isolation and provenance against the pinned run."""
    from .hazard import DEFAULT_POLICY, INPUT_FIELDS, OUTPUT_COLUMNS, SCORE_COLUMNS, integrate_pm_hazard, score_pm
    from .evidence_specialists import require_prediction_isolation
    from .lrtp import _verify_outputs

    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    upstream = Path(upstream_results) if upstream_results is not None else results.parent / 'stage4' / '4c'
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks, counts = [], [], {}

    def jsonl(path):
        with path.open(encoding='utf-8') as stream:
            return [json.loads(line) for line in stream]

    def compare_json(a, b, key, scope):
        for diff in _compare_evidence(json.dumps(a), json.dumps(b), key):
            diff.update(scope=scope, field=diff['field'].replace('LRTP_evidence', scope, 1))
            differences.append(diff)

    def compare_frame(a, b, fields, scope, numeric=()):
        plain = [c for c in fields if c != 'inchikey' and not c.endswith('_evidence')]
        differences.extend(_compare_qsar_frame(a, b, 'inchikey', {c: c for c in plain}, set(numeric), scope))
        left, right = a.set_index('inchikey'), b.set_index('inchikey')
        for key in left.index.intersection(right.index):
            for field in fields:
                if field.endswith('_evidence'):
                    compare_json(json.loads(left.at[key, field]), json.loads(right.at[key, field]), key, scope + '.' + field)
        checks.append({'scope': scope, 'rows': len(a), 'fields': len(fields)})

    try:
        previous = compare_annotations(baseline, upstream, output_dir / 'stage4c')
        if previous['status'] != 'passed':
            raise ValueError('Upstream Stage 4C regression failed.')
        manifest = _read_json(results / 'hazard_manifest.json')
        _verify_outputs(results, manifest)
        _verify_hash(DEFAULT_POLICY, manifest['policy_sha256'])
        _verify_hash(Path(__file__).with_name('hazard.py'), manifest['implementation_sha256'])
        _verify_hash(Path(__file__).with_name('qsar_models.json'), manifest['qsar_model_mapping_sha256'])
        if manifest['scoring_input_columns'] != INPUT_FIELDS or manifest['scoring_evidence_paths'] != ['hazard.P', 'hazard.M']:
            raise ValueError('The P/M input allowlist changed.')
        run = _read_json(baseline / 'run_manifest.json')
        checkpoint = baseline / run['stages']['5']['checkpoint']
        _verify_hash(checkpoint, run['stages']['5']['checkpoint_sha256'])
        metadata = _read_json(checkpoint)
        artifacts = {}
        for record in metadata['artifacts']:
            if record['artifact_id'] in ['compound_inventory_with_pbmt_hazard_csv', 'persistence_audit_json', 'mobility_audit_json']:
                path = baseline / record['path']
                _verify_hash(path, record['sha256'])
                artifacts[record['artifact_id']] = path
        old = _read_csv(artifacts['compound_inventory_with_pbmt_hazard_csv']).rename(columns={'Inchikey_std': 'inchikey'})
        prior = _read_csv(upstream / 'compound_annotated_evidence.csv')
        actual = _read_csv(results / 'compound_pm_hazard.csv')
        historical = _read_csv(results / 'pm_historical.csv')
        compare_frame(old, historical, OUTPUT_COLUMNS, 'historical_PM_fields', SCORE_COLUMNS)
        compare_frame(prior, actual, list(prior.columns), 'unchanged_stage4c_fields')
        require_prediction_isolation(actual)
        review = actual['qsar_identity_status'].eq('review_required')
        keys = set(actual.loc[review, 'inchikey'])
        clean = actual.loc[~review]
        compare_frame(old.loc[old['inchikey'].isin(clean['inchikey'])], clean, OUTPUT_COLUMNS, 'nonreview_PM_fields', SCORE_COLUMNS)
        if not actual.loc[review, SCORE_COLUMNS].eq('').all().all():
            raise ValueError('Current identity-review cohort unexpectedly has usable P/M scores; inspect curated fallback before updating this baseline.')
        if not actual.loc[review, ['persistence_available', 'mobility_available']].eq('False').all().all():
            raise ValueError('Identity-review P/M availability is incorrect.')
        for field in ['persistence_unavailable_reason', 'mobility_unavailable_reason']:
            if not actual.loc[review, field].eq('identity_review_required_no_curated_fallback').all():
                raise ValueError('Identity-review exclusion reason is missing.')
        if not historical['result_role'].eq('historical_reproduction_only').all() or not actual['pm_result_role'].eq('analysis_after_identity_isolation').all():
            raise ValueError('Historical and analysis roles are not explicit.')
        allowed = set(prior.columns) | set(OUTPUT_COLUMNS) | {'persistence_available', 'mobility_available', 'persistence_unavailable_reason', 'mobility_unavailable_reason', 'pm_result_role'}
        if set(actual.columns) != allowed:
            raise ValueError('Unexpected scoring fields outside Stage 5A.')
        for dimension in ['persistence', 'mobility']:
            expected = _read_json(artifacts[dimension + '_audit_json'])
            observed = jsonl(results / (dimension + '_historical_audit.jsonl'))
            analysis_audit = jsonl(results / (dimension + '_analysis_audit.jsonl'))
            for rows, label in [(expected, 'baseline'), (observed, 'historical'), (analysis_audit, 'analysis')]:
                if len(rows) != len(actual) or {r['compound_key'] for r in rows} != set(actual['inchikey']):
                    raise ValueError('Incomplete or duplicate ' + label + ' P/M audit keys.')
            old_map = {r['compound_key']: r for r in expected}
            for row in observed:
                compare_json(old_map[row['compound_key']], row, row['compound_key'], dimension + '_historical_audit')
            for row in analysis_audit:
                if row['compound_key'] not in keys:
                    compare_json(old_map[row['compound_key']], row, row['compound_key'], dimension + '_nonreview_audit')
            checks.append({'scope': dimension + '_audit', 'historical_rows': len(observed), 'nonreview_rows': len(clean)})
        # Recompute from current hashed inputs, never from historical Stage 5 scores.
        replay = integrate_pm_hazard(upstream)
        with tempfile.TemporaryDirectory(prefix='PlastPrior PM validation ') as directory:
            replay.write_reports(directory)
            rebuilt = _read_json(Path(directory) / 'hazard_manifest.json')
            if rebuilt != manifest:
                raise ValueError('P/M outputs or manifest differ from deterministic reconstruction.')
        checks.append({'scope': 'deterministic_reconstruction', 'files': len(manifest['output_sha256']) + 1})
        curated = [r for r in jsonl(upstream.parent / 'basic_evidence_audit.jsonl') if r.get('field_path') in ['hazard.P', 'hazard.M']]
        for filename, expected in [('pm_curated_source_links.jsonl', curated),
                                   ('identity_review_source_links.jsonl', jsonl(upstream / 'identity_review_source_links.jsonl'))]:
            if Counter(_semantic_digest(x) for x in expected) != Counter(_semantic_digest(x) for x in jsonl(results / filename)):
                raise ValueError('P/M source lineage changed: ' + filename)
        # Perturb annotation values and flags on every compound; P/M must remain invariant.
        altered = prior.copy()
        for column in altered.columns:
            if column.lower().startswith(('gic_', 'norman_')):
                altered[column] = 'annotation_invariance_probe'
        payloads = []
        for text in altered['db_extract_info']:
            value = json.loads(text)
            value['analytical_detectability'] = {'probe': 999}
            value['regulatory'] = {'GIC': {'probe': 999}}
            payloads.append(json.dumps(value))
        altered['db_extract_info'] = payloads
        probe, _ = score_pm(altered)
        # Compare CSV representations to retain the same missing/numeric conventions.
        probe = pd.read_csv(io.StringIO(probe.to_csv(index=False)), dtype=str, keep_default_na=False)
        compare_frame(actual, probe, OUTPUT_COLUMNS, 'GIC_NORMAN_scoring_invariance', SCORE_COLUMNS)
        impact = _read_csv(results / 'identity_review_pm_impacts.csv')
        expected_pairs = {(key, field) for key in keys for field in OUTPUT_COLUMNS}
        if len(impact) != len(expected_pairs) or set(zip(impact['inchikey'], impact['field'])) != expected_pairs:
            raise ValueError('Identity-review field impacts are incomplete or duplicated.')
        counts = {'compounds': len(actual), 'identity_review_compounds': len(keys), 'unaffected_compounds': len(clean),
                  'identity_review_source_links': len(jsonl(results / 'identity_review_source_links.jsonl')),
                  'curated_source_links': len(curated), 'field_impact_rows': len(impact),
                  'gic_name_review_required': int(actual['gic_name_review_required'].eq('True').sum()),
                  'gic_tag_expansion_review_required': int(actual['gic_shared_identifier_tag_expansion'].eq('True').sum())}
        for field in SCORE_COLUMNS:
            counts[field] = {'historical_available': int(historical[field].ne('').sum()),
                             'analysis_available': int(actual[field].ne('').sum()),
                             'excluded_review_values': int(historical.loc[historical['inchikey'].isin(keys), field].ne('').sum())}
    except (ValueError, KeyError, OSError, TypeError) as exc:
        differences.append({'scope': 'validation', 'key': '', 'field': 'precondition', 'expected': 'valid pinned inputs and outputs', 'actual': str(exc)})
    summary = {'status': 'passed' if not differences else 'failed', 'stage': '5A', 'counts': counts,
               'difference_count': len(differences), 'checks': checks,
               'comparison': 'Exact numeric values, basis strings and recursive evidence/audit JSON by full InChIKey. Identity-isolation differences are reported separately.'}
    pd.DataFrame(differences, columns=['scope', 'key', 'field', 'expected', 'actual']).to_csv(output_dir / 'pm_differences.csv', index=False, encoding='utf-8', lineterminator='\n')
    (output_dir / 'pm_validation_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def compare_bt_hazard(baseline, results, output_dir, upstream_results=None):
    """Validate historical B/T values, source lineage and permitted isolation effects."""
    from .hazard_bt import DEFAULT_POLICY, MODEL_FIELDS, OUTPUT_COLUMNS, SCORE_COLUMNS, integrate_bt_hazard, score_bt, _read_jsonl
    from .evidence_specialists import require_prediction_isolation
    from .lrtp import _verify_outputs
    from rdkit import rdBase

    baseline, results, output_dir = Path(baseline), Path(results), Path(output_dir)
    upstream = Path(upstream_results) if upstream_results is not None else results.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    differences, checks, counts = [], [], {}

    def compare_json(a, b, key, scope):
        for diff in _compare_evidence(json.dumps(a), json.dumps(b), key):
            diff.update(scope=scope, field=diff['field'].replace('LRTP_evidence', scope, 1))
            differences.append(diff)

    def compare_frame(a, b, fields, scope, numeric=()):
        plain = [c for c in fields if c != 'inchikey' and not c.endswith('_evidence')]
        differences.extend(_compare_qsar_frame(a, b, 'inchikey', {c: c for c in plain}, set(numeric), scope))
        left, right = a.set_index('inchikey'), b.set_index('inchikey')
        for key in left.index.intersection(right.index):
            for field in fields:
                if field.endswith('_evidence'):
                    compare_json(json.loads(left.at[key, field]), json.loads(right.at[key, field]), key, scope + '.' + field)
        checks.append({'scope': scope, 'rows': len(a), 'fields': len(fields)})

    try:
        previous = compare_pm_hazard(baseline, upstream, output_dir / 'stage5a')
        if previous['status'] != 'passed':
            raise ValueError('Upstream Stage 5A regression failed.')
        manifest = _read_json(results / 'bt_manifest.json')
        _verify_outputs(results, manifest)
        for file, field in [(DEFAULT_POLICY, 'policy_sha256'), (Path(__file__).with_name('hazard_bt.py'), 'implementation_sha256'),
                            (Path(__file__).with_name('hazard.py'), 'shared_pm_implementation_sha256'),
                            (Path(__file__).with_name('qsar_models.json'), 'qsar_model_mapping_sha256')]:
            _verify_hash(file, manifest[field])
        if manifest['runtime']['rdkit'] != rdBase.rdkitVersion:
            raise ValueError('RDKit version differs from the B/T calculation.')
        if manifest['scoring_input_columns'] != MODEL_FIELDS + ['qsar_smiles'] or manifest['scoring_evidence_paths'] != ['hazard.B', 'hazard.T']:
            raise ValueError('B/T scoring input allowlist changed.')
        run = _read_json(baseline / 'run_manifest.json')
        checkpoint = baseline / run['stages']['5']['checkpoint']
        _verify_hash(checkpoint, run['stages']['5']['checkpoint_sha256'])
        artifacts = {}
        for record in _read_json(checkpoint)['artifacts']:
            if record['artifact_id'] in ['compound_inventory_with_pbmt_hazard_csv', 'bioaccumulation_audit_json', 'toxicity_audit_json']:
                path = baseline / record['path']
                _verify_hash(path, record['sha256'])
                artifacts[record['artifact_id']] = path
        old = _read_csv(artifacts['compound_inventory_with_pbmt_hazard_csv']).rename(columns={'Inchikey_std': 'inchikey'})
        prior = _read_csv(upstream / 'compound_pm_hazard.csv')
        actual = _read_csv(results / 'compound_pbmt_hazard.csv')
        historical = _read_csv(results / 'bt_historical.csv')
        compare_frame(old, historical, OUTPUT_COLUMNS, 'historical_BT_fields', SCORE_COLUMNS)
        compare_frame(prior, actual, list(prior.columns), 'unchanged_stage5a_fields')
        require_prediction_isolation(actual)
        review = actual['qsar_identity_status'].eq('review_required')
        keys = set(actual.loc[review, 'inchikey'])
        clean = actual.loc[~review]
        compare_frame(old.loc[old['inchikey'].isin(clean['inchikey'])], clean, OUTPUT_COLUMNS, 'nonreview_BT_fields', SCORE_COLUMNS)
        if not historical['result_role'].eq('historical_reproduction_only').all() or not actual['bt_result_role'].eq('analysis_after_identity_isolation').all():
            raise ValueError('B/T output roles are not explicit.')
        allowed = set(prior.columns) | set(OUTPUT_COLUMNS) | {'bioaccumulation_available', 'toxicity_available', 'bioaccumulation_unavailable_reason', 'toxicity_unavailable_reason', 'bt_result_role'}
        if set(actual.columns) != allowed:
            raise ValueError('Unexpected fields outside B/T dimension assessment.')
        # Independently inspected frozen-cohort expectations, not derived from the new scoring kernel.
        expected_b = {'MQQRASSGRAFRIQ-UHFFFAOYSA-N': 1}
        expected_t = {'KXGFMDJXCMQABM-UHFFFAOYSA-N': 2, 'PSEGVHKUPXNGGJ-UHFFFAOYSA-N': 1,
                      'UZFMOKQJFYMBGY-UHFFFAOYSA-N': 2, 'WSGDRFHJFJRSFY-UHFFFAOYSA-N': 2,
                      'XVJWWMHPPKXKRU-UHFFFAOYSA-N': 0.5}
        if len(keys) != 15 or not (set(expected_b) | set(expected_t)) <= keys:
            raise ValueError('Identity-review cohort differs from the reviewed baseline.')
        for row in actual.loc[review].to_dict('records'):
            for dimension, expected in [('Bioaccumulation', expected_b), ('Toxicity', expected_t)]:
                value = row[dimension + '_score']
                want = expected.get(row['inchikey'])
                if (value == '') != (want is None) or (want is not None and Decimal(value) != Decimal(str(want))):
                    raise ValueError('Unexpected isolated B/T score: ' + row['inchikey'] + ' ' + dimension)
                if row[dimension.lower() + '_available'] != str(want is not None):
                    raise ValueError('Incorrect isolated B/T availability.')
                expected_reason = '' if want is not None else 'identity_review_required_no_independent_or_curated_fallback'
                if row[dimension.lower() + '_unavailable_reason'] != expected_reason:
                    raise ValueError('Missing isolated B/T availability reason.')
                evidence = json.loads(row[dimension + '_evidence'])
                expected_class = 'unavailable' if want is None else 'curated_fallback' if dimension == 'Toxicity' else 'independent_computation'
                if evidence['final_selection']['selected']['source_class'] != expected_class:
                    raise ValueError('Isolated score uses an unexpected evidence class.')
                block, entries = ('qsar_bcf_models', 'models') if dimension == 'Bioaccumulation' else ('qsar_toxicity', 'endpoints')
                if evidence[block]['selected'] is not None or any(r['usable'] or r['exclude_reason'] != 'identity_review_required' for r in evidence[block][entries]):
                    raise ValueError('Model evidence bypassed identity isolation.')
        for dimension in ['bioaccumulation', 'toxicity']:
            expected = _read_json(artifacts[dimension + '_audit_json'])
            observed = _read_jsonl(results / (dimension + '_historical_audit.jsonl'))
            analysis_audit = _read_jsonl(results / (dimension + '_analysis_audit.jsonl'))
            for rows in [expected, observed, analysis_audit]:
                if len(rows) != len(actual) or {r['compound_key'] for r in rows} != set(actual['inchikey']):
                    raise ValueError('Incomplete or duplicate B/T audit identities.')
            old_map = {r['compound_key']: r for r in expected}
            for row in observed:
                compare_json(old_map[row['compound_key']], row, row['compound_key'], dimension + '_historical_audit')
            for row in analysis_audit:
                if row['compound_key'] not in keys:
                    compare_json(old_map[row['compound_key']], row, row['compound_key'], dimension + '_nonreview_audit')
                elif row[dimension + '_from_qsar']:
                    raise ValueError('Unverified model values leaked into analysis audits.')
            checks.append({'scope': dimension + '_audit', 'historical_rows': len(observed), 'nonreview_rows': len(clean)})
        structures = _read_csv(results / 'bt_structure_mapping.csv')
        differences.extend(_compare_qsar_frame(old, structures, 'inchikey', {'Smile_std': 'scoring_smiles'}, set(), 'historical_structural_representation'))
        differences.extend(_compare_qsar_frame(prior, structures, 'inchikey', {'qsar_smiles': 'scoring_smiles', 'smiles_standard': 'source_smiles_standard', 'representative_record_id': 'representative_record_id'}, set(), 'local_structural_mapping'))
        if not structures['model_report_structure_used'].eq('False').all():
            raise ValueError('Model-report structure entered the B/T structural pathway.')
        checks.append({'scope': 'structural_mapping', 'rows': len(structures), 'text_changes': int(structures['text_changed_by_local_screening'].eq('True').sum())})
        replay = integrate_bt_hazard(upstream)
        with tempfile.TemporaryDirectory(prefix='PlastPrior BT validation ') as directory:
            replay.write_reports(directory)
            if _read_json(Path(directory) / 'bt_manifest.json') != manifest:
                raise ValueError('B/T outputs differ from deterministic reconstruction.')
        checks.append({'scope': 'deterministic_reconstruction', 'files': len(manifest['output_sha256']) + 1})
        curated = [r for r in _read_jsonl(upstream.parent / 'stage4' / 'basic_evidence_audit.jsonl') if r.get('field_path') in ['hazard.B', 'hazard.T']]
        for filename, expected in [('bt_curated_source_links.jsonl', curated), ('identity_review_source_links.jsonl', _read_jsonl(upstream / 'identity_review_source_links.jsonl'))]:
            if Counter(_semantic_digest(x) for x in expected) != Counter(_semantic_digest(x) for x in _read_jsonl(results / filename)):
                raise ValueError('B/T source lineage changed: ' + filename)
        altered = prior.copy()
        for column in altered.columns:
            if column.lower().startswith(('gic_', 'norman_')) or column == 'Basic | Smile_std':
                altered[column] = 'annotation_invariance_probe'
        payloads = []
        for text in altered['db_extract_info']:
            value = json.loads(text)
            value['analytical_detectability'] = {'probe': 999}
            value['regulatory'] = {'GIC': {'probe': 999}}
            value.setdefault('hazard', {})['toxicological_labels'] = {'probe': [999]}
            payloads.append(json.dumps(value))
        altered['db_extract_info'] = payloads
        probe, _ = score_bt(altered)
        probe = pd.read_csv(io.StringIO(probe.to_csv(index=False)), dtype=str, keep_default_na=False)
        compare_frame(actual, probe, OUTPUT_COLUMNS, 'annotation_and_report_structure_invariance', SCORE_COLUMNS)
        impacts = _read_csv(results / 'identity_review_bt_impacts.csv')
        pairs = {(key, field) for key in keys for field in OUTPUT_COLUMNS}
        if len(impacts) != len(pairs) or set(zip(impacts['inchikey'], impacts['field'])) != pairs or impacts['change_reason'].eq('').any():
            raise ValueError('B/T isolation impact ledger is incomplete.')
        counts = {**manifest['counts'], 'unaffected_compounds': len(clean), 'field_impact_rows': len(impacts)}
        for column in SCORE_COLUMNS:
            old_review = historical.set_index('inchikey').loc[sorted(keys), column]
            new_review = actual.set_index('inchikey').loc[sorted(keys), column]
            counts[column] = {'historical_available': int(historical[column].ne('').sum()), 'analysis_available': int(actual[column].ne('').sum()),
                              'review_available': int(new_review.ne('').sum()), 'newly_unavailable': int((old_review.ne('') & new_review.eq('')).sum()),
                              'increased_review_scores': sum(Decimal(b) > Decimal(a) for a, b in zip(old_review, new_review) if a and b)}
    except (ValueError, KeyError, OSError, TypeError) as exc:
        differences.append({'scope': 'validation', 'key': '', 'field': 'precondition', 'expected': 'valid pinned B/T inputs and outputs', 'actual': str(exc)})
    summary = {'status': 'passed' if not differences else 'failed', 'stage': '5B', 'counts': counts,
               'difference_count': len(differences), 'checks': checks,
               'comparison': 'Exact numeric values, basis strings and recursive evidence/audit JSON by full InChIKey; permitted identity-isolation effects are reported separately.'}
    pd.DataFrame(differences, columns=['scope', 'key', 'field', 'expected', 'actual']).to_csv(output_dir / 'bt_differences.csv', index=False, encoding='utf-8', lineterminator='\n')
    (output_dir / 'bt_validation_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Frozen historical run directory.")
    parser.add_argument("--results", type=Path, required=True, help="Current report directory for the selected stage.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Validation report directory.")
    parser.add_argument("--stage", choices=["identity", "qsar", "lrtp", "evidence", "specialists", "annotations", "hazard-pm", "hazard-bt", "exposure-inputs", "exposure", "priority", "ranking"], default="identity")
    parser.add_argument("--upstream-results", type=Path, help="Upstream outputs: Stage 2 for QSAR, Stage 3A for LRTP, Stage 3B for evidence, Stage 4A for specialists, Stage 4B for annotations, Stage 4C for hazard-pm, Stage 5A for hazard-bt; inferred from the standard layout by default.")
    parser.add_argument("--data-root", type=Path, help="Local frozen inputs for exposure-inputs validation; defaults to project data.")
    args = parser.parse_args(argv)
    if args.stage == "ranking":
        from .ranking_validation import compare_ranking
        report = compare_ranking(args.baseline, args.results, args.output_dir, args.upstream_results, args.data_root)
    elif args.stage == "priority":
        from .priority_validation import compare_priority
        report = compare_priority(args.baseline, args.results, args.output_dir, args.upstream_results, args.data_root)
    elif args.stage == "exposure":
        from .exposure_validation import compare_exposure_scores
        report = compare_exposure_scores(args.baseline, args.results, args.output_dir, args.upstream_results, args.data_root)
    elif args.stage == "exposure-inputs":
        from .exposure_validation import compare_exposure_inputs
        report = compare_exposure_inputs(args.baseline, args.results, args.output_dir, args.upstream_results, args.data_root)
    elif args.stage == "identity":
        report = compare_identity(args.baseline, args.results, args.output_dir)
    else:
        validator = {"qsar": compare_qsar, "lrtp": compare_lrtp, "evidence": compare_basic_evidence, "specialists": compare_specialist_evidence, "annotations": compare_annotations, "hazard-pm": compare_pm_hazard, "hazard-bt": compare_bt_hazard}[args.stage]
        report = validator(args.baseline, args.results, args.output_dir, args.upstream_results)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
