"""Ensure equal totals cannot hide altered structures or missing memberships."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.inputs import _file_hash
from plastprior.validation import compare_identity


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="PlastPrior regression ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.baseline = self.root / "baseline"
        self.results = self.root / "stage2"
        self.output = self.root / "validation"
        self.baseline.mkdir()
        self.results.mkdir()
        self.declaration = self.root / "baseline.json"
        self.key = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        raw = {"Name": "Ethanol", "CAS": "64-17-5", "Smile": "CCO", "Inchikey": self.key,
               "source_db": "Synthetic", "source_smiles_field": ""}
        resolved = {**raw, "Smile_std": "CCO", "Smile_isomeric_std": "CCO", "Inchikey_std": self.key,
                    "Inchikey14": self.key[:14], "Qsar_inchikey": self.key, "stereo_status": "not_stereogenic",
                    "Name_std": "Ethanol", "resolved_by": "reported_smile", "confidence_level": "A",
                    "reported_derived_inchikey_status": "exact_match"}
        compound = {**resolved, "best_confidence_level": "A", "n_records": "2", "source_dbs": "Synthetic",
                    "source_info_json": json.dumps([resolved, resolved]),
                    "reported_derived_inchikey_statuses_json": '["exact_match"]'}
        cas = {"CAS": "64-17-5", "cas_mapping_status": "one_to_one", "cas_mapping_count": "1",
               "cas_connectivity_count": "1", "source_record_count": "2", "inchikeys_json": json.dumps([self.key]),
               "inchikey14s_json": json.dumps([self.key[:14]]), "source_dbs_json": '["Synthetic"]'}
        artifacts = []
        for name, rows in (("core_identifier_table_csv", [raw, raw]),
                           ("compound_records_resolved_csv", [resolved, resolved]),
                           ("compound_inventory_by_inchikey_csv", [compound]),
                           ("cas_inchikey_mapping_audit_csv", [cas])):
            path = self.baseline / (name + ".csv")
            self.csv(path, rows)
            artifacts.append({"artifact_id": name, "path": path.name, "sha256": _file_hash(path)})
        stages = {}
        for number in ("1", "2"):
            path = self.baseline / ("stage" + number + ".json")
            self.json(path, {"artifacts": artifacts[:1] if number == "1" else artifacts[1:]})
            stages[number] = {"checkpoint": path.name, "checkpoint_sha256": _file_hash(path)}
        self.json(self.baseline / "input_manifest.json", {"records": [{"filename": "source.csv", "sha256": "input-hash"}]})
        run = {"run_id": "synthetic", "input_manifest_sha256": _file_hash(self.baseline / "input_manifest.json"),
               "stages": stages, "environment": {"package_versions": {"rdkit": "2026.3.1"}},
               "repository": {"git_dirty": True}}
        self.json(self.baseline / "run_manifest.json", run)
        self.json(self.declaration, {"run_manifest_sha256": _file_hash(self.baseline / "run_manifest.json"),
                                    "parsed_without_key": 0})
        sources, identities = [], []
        for i in (1, 2):
            source = {"record_id": f"row-{i}", "table_id": "synthetic", "source_record_number": str(i),
                      "included": "True", "name_reported": "Ethanol", "cas_reported": "64-17-5",
                      "smiles_reported": "CCO", "inchikey_reported": self.key}
            sources.append(source)
            identities.append({**source, "smiles_standard": "CCO", "smiles_isomeric": "CCO", "inchikey": self.key,
                               "connectivity_key": self.key[:14], "qsar_inchikey": self.key, "stereo_status": "not_stereogenic",
                               "name_resolved": "Ethanol", "resolution_route": "reported_smile", "route_tier": "A",
                               "reported_derived_status": "exact_match", "aggregation_eligible": "True"})
        new_compound = {**identities[0], "representative_record_id": "row-1", "n_records": "2",
                        "source_tables_json": '["synthetic"]', "reported_derived_statuses_json": '["exact_match"]'}
        new_cas = {"cas": "64-17-5", "mapping_status": "one_to_one", "inchikey_count": "1", "connectivity_count": "1",
                   "source_record_count": "2", "inchikeys_json": json.dumps([self.key]),
                   "connectivity_keys_json": json.dumps([self.key[:14]]), "source_tables_json": '["synthetic"]'}
        for name, rows in (("source_records", sources), ("resolved_records", identities),
                           ("compound_inventory", [new_compound]), ("cas_mapping_audit", [new_cas]),
                           ("compound_memberships", [{"inchikey": self.key, "record_id": f"row-{i}",
                                                     "is_representative": str(i == 1)} for i in (1, 2)])):
            self.csv(self.results / (name + ".csv"), rows)
        self.refresh_manifests()

    def json(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def csv(self, path, rows):
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8", lineterminator="\n")

    def refresh_manifests(self):
        source = {"catalog_sha256": "catalog", "input_files": [{"filename": "source.csv", "sha256": "input-hash"}],
                  "output_sha256": {"source_records.csv": _file_hash(self.results / "source_records.csv")}}
        identity = {"catalog_sha256": "catalog", "source_records_sha256": _file_hash(self.results / "source_records.csv"),
                    "source_assembly_manifest": source, "reference_inputs": [], "runtime": {"rdkit": "2026.3.1"},
                    "output_sha256": {p.name: _file_hash(p) for p in self.results.glob("*.csv") if p.name != "source_records.csv"}}
        self.json(self.results / "source_record_manifest.json", source)
        self.json(self.results / "identity_manifest.json", identity)

    def compare(self):
        with patch("plastprior.validation.BASELINE", self.declaration), patch(
            "plastprior.validation.SOURCE_TABLES", {"Synthetic": "synthetic"}
        ):
            return compare_identity(self.baseline, self.results, self.output)

    def test_exact_results_pass_and_preserve_duplicate_members(self):
        report = self.compare()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["member_links_compared"], 2)

    def test_same_counts_with_changed_record_structure_fail(self):
        path = self.results / "resolved_records.csv"
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
        data.loc[1, "smiles_standard"] = "CO"
        self.csv(path, data)
        self.refresh_manifests()
        report = self.compare()
        self.assertEqual(report["status"], "failed")
        differences = pd.read_csv(self.output / "validation_differences.csv")
        self.assertIn("smiles_standard", differences["field"].tolist())

    def test_missing_member_fails_even_when_inventory_totals_are_unchanged(self):
        path = self.results / "compound_memberships.csv"
        self.csv(path, pd.read_csv(path, dtype=str).iloc[:1])
        self.refresh_manifests()
        report = self.compare()
        self.assertEqual(report["status"], "failed")
        self.assertGreater(report["unexplained_differences"], 0)

    def test_stale_output_hash_fails_before_comparison(self):
        path = self.results / "resolved_records.csv"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        report = self.compare()
        self.assertEqual(report["status"], "failed")
        self.assertIn("Fingerprint mismatch", report["error"])

    def test_baseline_replacement_fails(self):
        self.json(self.baseline / "run_manifest.json", {"run_id": "replacement"})
        self.assertEqual(self.compare()["status"], "failed")

    def test_qsar_qc_smiles_difference_uses_record_level_reference(self):
        path = self.baseline / "compound_inventory_by_inchikey_csv.csv"
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
        data.loc[0, "Smile_std"] = "post-QC-string"
        self.csv(path, data)
        checkpoint_path = self.baseline / "stage2.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        for artifact in checkpoint["artifacts"]:
            if artifact["path"] == path.name:
                artifact["sha256"] = _file_hash(path)
        self.json(checkpoint_path, checkpoint)
        run_path = self.baseline / "run_manifest.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["stages"]["2"]["checkpoint_sha256"] = _file_hash(checkpoint_path)
        self.json(run_path, run)
        self.json(self.declaration, {"run_manifest_sha256": _file_hash(run_path), "parsed_without_key": 0})
        report = self.compare()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["legacy_qsar_qc_smiles_changes"], 1)


if __name__ == "__main__":
    unittest.main()
