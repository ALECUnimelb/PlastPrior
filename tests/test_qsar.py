"""Test frozen-batch alignment, scientific identity warnings and lossless provenance."""

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from plastprior.identity import IdentityResult, _standardize
from plastprior.inputs import _file_hash
from plastprior.qsar import (_csv_hash, _identity_audit, _input_manifest, _numeric_projection,
                            _read_report, _screen, integrate_qsar)
from plastprior.validation import _compare_qsar_frame


class QSARTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="PlastPrior QSAR ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "Vega output").mkdir()
        self.path = self.root / "Vega output" / "report_TEST.txt"
        self.policy = {"mw_min": 100.0, "mw_max": 1000.0, "heavy_halogen_threshold": 4, "metals": ["Na", "Fe"]}
        self.header = ["No.", "Id", "SMILES", "Assessment", "Predicted value [mg/L]", "ADI", "Remarks"]
        self.model = {"id": "test", "filename": self.path.name, "name": "Test", "model_metadata": "Test (version 1)",
                      "calculation_metadata": "Core (version 1)", "encoding": "utf-8", "headers": self.header,
                      "allowed_row_widths": [7], "predictions": [{"column": "Predicted value [mg/L]", "unit": "mg/L"}],
                      "quality_columns": ["Assessment", "ADI", "Remarks"],
                      "merge_columns": ["Predicted value [mg/L]", "Assessment", "ADI"],
                      "numeric_columns": ["Predicted value [mg/L]", "ADI"]}

    def write_report(self, rows):
        self.path.write_text("VEGA\nTest (version 1)\nCore (version 1)\n\n" + "\t".join(self.header) + "\n" +
                             "\n".join("\t".join(map(str, row)) for row in rows) + "\n", encoding="utf-8")
        self.model["sha256"] = _file_hash(self.path)

    def compound(self, smiles, number=1):
        structure = _standardize(smiles)
        return {**structure, "representative_record_id": f"record-{number}", "name_resolved": "Example"}

    def fixture(self, input_smiles="CCCCCCCC", report_smiles=None, review_rows=None):
        compound = self.compound(input_smiles)
        compounds = pd.DataFrame([compound])
        member = {"inchikey": compound["inchikey"], "record_id": "record-1", "is_representative": True}
        record = {**compound, "record_id": "record-1", "source_id": "source", "table_id": "table", "smiles_reported": input_smiles}
        empty = pd.DataFrame()
        identity = IdentityResult(pd.DataFrame([record]), compounds, pd.DataFrame([member]), empty, empty, empty, empty,
                                  {"policy_version": "synthetic-v1"})
        manifest = _input_manifest(_screen(compounds, self.policy))
        self.write_report([[1, "Molecule 1", report_smiles or input_smiles, "LOW reliability", "12.50", "0.4", "-"]])
        config = {"schema_version": 1, "policy_version": "synthetic-v1", "scope": "Stage 3A", "screening": self.policy,
                  "models": [self.model], "frozen_batch": {"input_manifest_sha256": _csv_hash(manifest),
                  "input_smiles_sha256": _csv_hash(manifest[["Smile_std"]], header=False), "identity_review_rows": review_rows or []},
                  "legacy_merge_columns": ["Basic | Inchikey14", "Basic | Smile_std", *["Test | " + c for c in self.model["merge_columns"]]],
                  "known_absent_columns": [], "legacy_excel_missing_tokens": ["", "N/A", "NA"]}
        path = self.root / "models.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return identity, path

    def test_screening_separates_exclusion_and_warnings(self):
        compounds = pd.DataFrame([self.compound(s, n) for n, s in enumerate([
            "CCO", "CCCCCCCC", "CCCCCCCC.[Na+]", "CC(Cl)(Cl)C(Cl)(Cl)C", "CCCCCCCC[NH3+]"] , 1)])
        result = _screen(compounds, self.policy).set_index("inchikey")
        ethanol = result.loc[_standardize("CCO")["inchikey"]]
        self.assertFalse(ethanol["keep_for_vega"])
        self.assertEqual(ethanol["qc_flags"], "mw_out_of_range")
        halogenated = result.loc[_standardize("CC(Cl)(Cl)C(Cl)(Cl)C")["inchikey"]]
        self.assertTrue(halogenated["keep_for_vega"])
        self.assertIn("heavy_halogenated", halogenated["qc_flags"])
        self.assertFalse(result.loc[_standardize("CCCCCCCC.[Na+]")["inchikey"], "keep_for_vega"])
        self.assertTrue(result.loc[_standardize("CCCCCCCC[NH3+]")["inchikey"], "keep_for_vega"])

    def test_full_identities_share_one_qsar_input_without_inventory_collapse(self):
        identity, path = self.fixture("N[C@@H](CC)C(=O)O")
        other = self.compound("N[C@H](CC)C(=O)O", 2)
        frame = pd.concat([identity.compounds, pd.DataFrame([other])], ignore_index=True)
        screening = _screen(frame, self.policy)
        self.assertEqual(len(frame), 2)
        self.assertEqual(len(_input_manifest(screening)), 1)

    def test_radical_difference_is_never_verified_even_when_row_mapping_is_allowed(self):
        identity, path = self.fixture("CCCCCCCC[O]", "CCCCCCCCO", [1])
        result = integrate_qsar(identity, self.root, models_path=path)
        row = result.identity_audit.iloc[0]
        self.assertEqual(row["reason"], "formula_and_radical_representation_difference")
        self.assertNotEqual(row["input_formula"], row["report_formula"])
        self.assertFalse(result.compounds.iloc[0]["qsar_identity_verified"])
        self.assertEqual(result.compounds.iloc[0]["Test | Predicted value [mg/L]"], 12.5)
        self.assertEqual(result.anomaly_sources["record_id"].tolist(), ["record-1"])
        self.assertEqual(result.anomaly_reports.iloc[0]["source_sha256"], self.model["sha256"])

    def test_unexpected_identity_mismatch_stops_integration(self):
        identity, path = self.fixture("CCCCCCCC[O]", "CCCCCCCCO")
        with self.assertRaisesRegex(ValueError, "exceptions differ"):
            integrate_qsar(identity, self.root, models_path=path)

    def test_kekulization_failure_retains_parser_diagnostics(self):
        input_smiles = "c1csc(C2=S=C(c3cccs3)c3nsnc32)c1"
        report_smiles = "n1c3c(ns1)c(c2cccs2)sc3c4cccs4"
        identity, path = self.fixture(input_smiles, report_smiles, [1])
        result = integrate_qsar(identity, self.root, models_path=path)
        self.assertEqual(result.identity_audit.iloc[0]["reason"], "report_aromaticity_kekulization_failure")
        self.assertIn("KekulizeException", result.identity_audit.iloc[0]["report_parse_problems_json"])

    def test_changed_batch_or_report_bytes_cannot_be_silently_reused(self):
        identity, path = self.fixture()
        identity.compounds.loc[0, "smiles_standard"] = "CCCCCCCCC"
        with self.assertRaisesRegex(ValueError, "input batch differs"):
            integrate_qsar(identity, self.root, models_path=path)
        identity, path = self.fixture()
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "frozen version"):
            integrate_qsar(identity, self.root, models_path=path)

    def test_reordered_numbering_fails_even_with_current_file_hash(self):
        identity, path = self.fixture()
        self.write_report([[2, "Molecule 2", "CCCCCCCC", "Good", "12.5", "1", "-"]])
        config = json.loads(path.read_text(encoding="utf-8"));config["models"] = [self.model]
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "row numbering"):
            integrate_qsar(identity, self.root, models_path=path)

    def test_variable_width_rows_preserve_raw_cells_and_legacy_positions(self):
        self.model["allowed_row_widths"] = [6, 7, 8]
        rows = [[1, "A", "C", "Good", "2.0", "0.8", "extra", "note"],
                [2, "B", "C", "Good", "2.0", "0.8", "-"],
                [3, "C", "C", "[Error]", "-", "-"]]
        self.write_report(rows)
        frame, audit, _ = _read_report(self.path, self.model)
        self.assertEqual(frame.iloc[0]["Remarks"], "note")
        self.assertEqual(frame.iloc[1]["Extra AD column 1"], "-")
        self.assertEqual(frame.iloc[1]["Remarks"], "")
        self.assertEqual(json.loads(audit[1]["raw_cells_json"]), list(map(str, rows[1])))
        self.assertEqual(len(audit), 3)

    def test_unknown_row_width_is_rejected(self):
        self.write_report([[1, "A", "C", "Good", "2", "1", "extra", "note"]])
        with self.assertRaisesRegex(ValueError, "row width"):
            _read_report(self.path, self.model)

    def test_raw_missing_tokens_and_invalid_numeric_text_are_distinct(self):
        raw = pd.Series(["1.20", "-", "", "bad", "0"])
        values, status = _numeric_projection(raw)
        self.assertEqual(values.iloc[0], 1.2)
        self.assertEqual(values.iloc[-1], 0)
        self.assertEqual(status.tolist(), ["numeric", "source_missing_token", "source_missing_token", "unparseable_numeric_token", "numeric"])
        self.assertEqual(raw.iloc[3], "bad")

    def test_integration_keeps_upstream_fields_and_low_adi_without_scoring(self):
        identity, path = self.fixture()
        before = identity.compounds.copy(deep=True)
        result = integrate_qsar(identity, self.root, models_path=path)
        pd.testing.assert_frame_equal(before, identity.compounds)
        self.assertEqual(result.compounds.iloc[0]["Test | ADI"], 0.4)
        self.assertTrue(result.compounds.iloc[0]["qsar_identity_verified"])
        self.assertFalse(any(c.startswith("LRTP_") for c in result.compounds.columns))
        out = self.root / "outputs";result.write_reports(out)
        manifest = json.loads((out / "qsar_manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["output_sha256"].items():
            self.assertEqual(_file_hash(out / name), digest)

    def test_legacy_text_na_projection_preserves_raw_values_and_conversion_evidence(self):
        identity, path = self.fixture()
        self.write_report([[1, "Molecule 1", "CCCCCCCC", "N/A", "12.5", "0.4", "-"]])
        config = json.loads(path.read_text(encoding="utf-8"));config["models"] = [self.model]
        path.write_text(json.dumps(config), encoding="utf-8")
        result = integrate_qsar(identity, self.root, models_path=path)
        self.assertEqual(result.predictions.iloc[0]["Test | Assessment"], "N/A")
        self.assertTrue(pd.isna(result.compounds.iloc[0]["Test | Assessment"]))
        self.assertEqual(result.missing_value_audit.iloc[0]["raw_value"], "N/A")

    def test_regression_compares_values_not_just_counts(self):
        prior = pd.DataFrame({"key": ["a", "b"], "value": ["1.2", ""]})
        current = pd.DataFrame({"key": ["a", "b"], "value": ["1.20", ""]})
        compare = lambda: _compare_qsar_frame(prior, current, "key", {"value": "value"}, {"value"}, "test")
        self.assertEqual(compare(), [])
        current.loc[1, "value"] = "0"
        self.assertEqual(len(compare()), 1)
        current.loc[0, "value"] = "1.20000000000001"
        self.assertEqual(len(compare()), 2)


if __name__ == "__main__":
    unittest.main()
