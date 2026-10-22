"""Input-reader tests using small synthetic files, without research data."""

import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.inputs import inspect_inputs, load_catalog, read_source_table, resolve_data_root
from main import main


class InputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="PlastPrior input test ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sources = self.root / "SourceDatabase"
        self.sources.mkdir()
        self.catalog = self.root / "sources.json"
        self.spec = {"schema_version": 1, "sources": [{
            "id": "example", "label": "Synthetic source", "filename": "example.csv",
            "role": "test fixture", "version": None, "snapshot_date": None,
            "notes": "Synthetic input; not research observations.", "reference": "",
            "tables": [{"id": "records", "sheet": None, "header": 0,
                        "role": "test records", "required_columns": ["id", "name"]}],
        }], "supporting_inputs": []}

    def save_catalog(self):
        self.catalog.write_text(json.dumps(self.spec), encoding="utf-8")

    def inspect(self):
        self.save_catalog()
        return inspect_inputs(self.root, catalog_path=self.catalog)

    def test_csv_counts_multiline_cells_and_preserves_literal_na(self):
        (self.sources / "example.csv").write_text(
            'id,name\n001,NA\n002,"two\nlines"\n,\n', encoding="utf-8")
        with patch("plastprior.inputs.CSV_CHUNK_SIZE", 1):
            report = self.inspect()
        self.assertTrue(report.passed)
        self.assertEqual(report.tables.iloc[0]["parsed_rows"], 3)
        self.assertEqual(report.tables.iloc[0]["nonempty_rows"], 2)
        self.assertEqual(report.sources.iloc[0]["version"], "Not recorded")
        frame = read_source_table("example", data_root=self.root, catalog_path=self.catalog)
        self.assertEqual(frame.iloc[0]["id"], "001")
        self.assertEqual(frame.iloc[0]["name"], "NA")
        self.assertEqual(frame.iloc[1]["name"], "two\nlines")

    def test_missing_file_is_not_reported_as_zero_records(self):
        report = self.inspect()
        self.assertFalse(report.passed)
        self.assertFalse(report.sources_passed)
        self.assertTrue(report.supporting_present)
        self.assertEqual(report.sources.iloc[0]["status"], "MISSING")
        self.assertTrue(pd.isna(report.tables.iloc[0]["parsed_rows"]))
        with self.assertRaisesRegex(ValueError, "inspection failed"):
            report.require_complete()
        with self.assertRaisesRegex(ValueError, "Source inspection failed"):
            report.require_sources()

    def test_wrong_schema_fails_instead_of_counting_wrong_table(self):
        (self.sources / "example.csv").write_text("unrelated\nvalue\n", encoding="utf-8")
        report = self.inspect()
        self.assertFalse(report.passed)
        self.assertIn("Missing required column", report.tables.iloc[0]["detail"])

    def test_excel_uses_declared_sheet_and_header_offset(self):
        source = self.spec["sources"][0]
        source["filename"] = "example.xlsx"
        source["tables"][0].update(sheet="Selected", header=2)
        with pd.ExcelWriter(self.sources / "example.xlsx", engine="openpyxl") as writer:
            pd.DataFrame({"unrelated": [1, 2, 3]}).to_excel(writer, sheet_name="Other", index=False)
            pd.DataFrame({"id": ["a", "b"], "name": ["alpha", "beta"]}).to_excel(
                writer, sheet_name="Selected", startrow=2, index=False)
        report = self.inspect()
        self.assertTrue(report.passed)
        self.assertEqual(report.tables.iloc[0]["parsed_rows"], 2)
        self.assertEqual(report.tables.iloc[0]["header_row"], 3)
        source["tables"][0]["sheet"] = "Absent"
        self.assertFalse(self.inspect().passed)

    def test_corrupt_excel_is_reported_without_aborting_other_sources(self):
        source = self.spec["sources"][0]
        source["filename"] = "example.xlsx"
        source["tables"][0]["sheet"] = "Selected"
        (self.sources / "example.xlsx").write_text("not an Excel workbook", encoding="utf-8")
        report = self.inspect()
        self.assertFalse(report.passed)
        self.assertEqual(report.tables.iloc[0]["status"], "ERROR")

    def test_supporting_inputs_require_specific_files(self):
        (self.sources / "example.csv").write_text("id,name\na,alpha\n", encoding="utf-8")
        self.spec["supporting_inputs"] = [{"label": "Evidence", "folder": "Evidence",
                                           "required_files": ["required.txt"]}]
        (self.root / "Evidence").mkdir()
        (self.root / "Evidence" / "unrelated.txt").write_text("test", encoding="utf-8")
        report = self.inspect()
        self.assertFalse(report.passed)
        self.assertTrue(report.sources_passed)
        self.assertFalse(report.supporting_present)
        report.require_sources()
        with self.assertRaisesRegex(ValueError, "inspection failed"):
            report.require_complete()
        self.assertEqual(report.supporting.iloc[0]["status"], "MISSING")

        output_dir = self.root / "reports"
        with patch("main.inspect_inputs", return_value=report), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--output-dir", str(output_dir)]), 0)
            self.assertEqual(main(["--output-dir", str(output_dir), "--require-supporting-inputs"]), 1)
        self.assertIn("Stage 1 source inspection: Passed", output.getvalue())
        self.assertIn("Supporting inputs: Incomplete", output.getvalue())
        saved = pd.read_csv(output_dir / "supporting_inputs.csv", keep_default_na=False)
        self.assertEqual(saved.iloc[0]["status"], "MISSING")

        (self.root / "Evidence" / "required.txt").write_text("test", encoding="utf-8")
        self.assertTrue(self.inspect().passed)

    def test_source_failure_stops_cli_with_or_without_strict_presence_checks(self):
        report = self.inspect()
        with patch("main.inspect_inputs", return_value=report), \
                patch("main.build_source_records") as assemble, redirect_stdout(io.StringIO()):
            for options in ([], ["--require-supporting-inputs"], ["--assemble-records"], ["--resolve-identities"]):
                self.assertEqual(main(["--output-dir", str(self.root / "reports"), *options]), 1)
            assemble.assert_not_called()

    def test_reports_preserve_provenance_hashes_and_dimensions(self):
        (self.sources / "example.csv").write_text("id,name\n001,NA\n", encoding="utf-8")
        self.spec["sources"][0]["notes"] = "Source note with a comma, and a second line.\nRetained."
        report = self.inspect()
        output_dir = self.root / "inspection reports"
        report.write_reports(output_dir)
        saved = pd.read_csv(output_dir / "source_inventory.csv", keep_default_na=False)
        self.assertEqual(saved.iloc[0]["sha256"], report.sources.iloc[0]["sha256"])
        self.assertEqual(saved.iloc[0]["provenance_note"], self.spec["sources"][0]["notes"])
        tables = pd.read_csv(output_dir / "table_dimensions.csv")
        self.assertEqual(tables.iloc[0]["parsed_rows"], 1)
        self.assertTrue(pd.read_csv(output_dir / "supporting_inputs.csv").empty)

    def test_duplicate_identifiers_are_rejected(self):
        self.spec["sources"].append(self.spec["sources"][0].copy())
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "unique"):
            load_catalog(self.catalog)

    def test_ambiguous_table_selection_is_rejected(self):
        self.spec["sources"][0]["tables"].append({
            "id": "other", "sheet": "Other", "header": 0,
            "role": "test records", "required_columns": ["id"]})
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, "table_id"):
            read_source_table("example", data_root=self.root, catalog_path=self.catalog)

    def test_empty_table_fails(self):
        (self.sources / "example.csv").write_text("id,name\n", encoding="utf-8")
        self.assertFalse(self.inspect().passed)

    def test_relative_data_root_uses_project_directory(self):
        with patch("plastprior.inputs.PROJECT_ROOT", self.root):
            self.assertEqual(resolve_data_root("data"), self.root / "data")
            self.assertEqual(resolve_data_root(self.sources), self.sources)


if __name__ == "__main__":
    unittest.main()
