"""Compare Stage 2 outputs with a fingerprinted historical run, without executing it."""

from __future__ import annotations

import argparse
from collections import Counter
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Frozen historical run directory.")
    parser.add_argument("--results", type=Path, required=True, help="Current stage2 report directory.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Validation report directory.")
    args = parser.parse_args(argv)
    report = compare_identity(args.baseline, args.results, args.output_dir)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
