"""Verify provenance, explicit field selection and inclusion without chemical matching."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.inputs import build_source_records


class SourceRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="PlastPrior source records ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source_dir = self.root / "SourceDatabase"
        self.source_dir.mkdir()
        self.path = self.source_dir / "inventory.csv"
        self.catalog = self.root / "sources.json"
        self.mapping = {
            "scope": "candidate_inventory", "native_id_column": "local_id",
            "fields": {"name_reported": ["Name"], "cas_reported": ["CAS"],
                       "smiles_reported": ["Isomeric", "Canonical"], "inchikey_reported": ["Key"]},
            "required_for_inclusion": [],
        }
        self.table = {"id": "inventory", "sheet": None, "header": 0,
                      "role": "chemical inventory", "required_columns": ["Name"],
                      "record_mapping": self.mapping}
        self.spec = {"schema_version": 1, "sources": [{
            "id": "example", "filename": self.path.name, "tables": [self.table]}],
            "record_assembly_policy": {"version": "synthetic-v1", "missing_tokens": ["", "NA", "N/A"]}}

    def build(self):
        self.catalog.write_text(json.dumps(self.spec), encoding="utf-8")
        return build_source_records(self.root, catalog_path=self.catalog)

    def write_csv(self, rows):
        self.path.write_text("local_id,Name,CAS,Isomeric,Canonical,Key\n" + rows, encoding="utf-8")

    def test_preserves_raw_values_and_declared_fallback_without_deduplication(self):
        self.write_csv("001, Example , 50-00-0 ,NA, C=O ,KEY\n001, Example , 50-00-0 ,NA, C=O ,KEY\n")
        before = self.path.read_bytes()
        result = self.build()
        row = result.records.iloc[0]
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records["record_id"].nunique(), 2)
        self.assertEqual(row["source_native_id"], "001")
        self.assertEqual(row["name_reported"], " Example ")
        self.assertEqual(row["cas_reported"], " 50-00-0 ")
        self.assertEqual(row["smiles_reported"], " C=O ")
        self.assertEqual(row["smiles_reported_column"], "Canonical")
        self.assertEqual(json.loads(row["reported_fields_json"])["Isomeric"], "NA")
        self.assertEqual(row["inchikey_reported"], "KEY")  # Supplied, not chemically validated.
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(result.records["record_id"].tolist(), self.build().records["record_id"].tolist())
        self.path.write_text(self.path.read_text(encoding="utf-8") + "002,Next,,,,\n", encoding="utf-8")
        self.assertNotEqual(row["record_id"], self.build().records.iloc[0]["record_id"])

    def test_missing_required_values_are_retained_with_explicit_reasons(self):
        self.mapping["required_for_inclusion"] = ["smiles_reported", "inchikey_reported"]
        self.write_csv("1,A,50-00-0, ,N/A,KEY\n2,B,50-00-0,C=O,,NA\n3,C,,not-a-valid-smiles,,KEY\n")
        result = self.build()
        self.assertEqual(result.records["included"].tolist(), [False, False, True])
        self.assertEqual(result.records["exclusion_reason"].tolist(),
                         ["missing_required_smiles_reported", "missing_required_inchikey_reported", ""])
        self.assertEqual(result.summary.iloc[0]["excluded_records"], 2)
        self.assertEqual(result.summary.iloc[0]["name_available"], 1)
        self.assertEqual(result.summary.iloc[0]["cas_available"], 0)
        self.assertEqual(result.summary.iloc[0]["availability_denominator"], "included_records")

    def test_unsupplied_fields_and_missing_native_ids_do_not_exclude_inventory_rows(self):
        self.mapping["native_id_column"] = None
        self.mapping["fields"]["smiles_reported"] = []
        self.mapping["fields"]["inchikey_reported"] = []
        self.write_csv("1,A,50-00-0,C=O,,KEY\n")
        row = self.build().records.iloc[0]
        self.assertTrue(row["included"])
        self.assertFalse(row["smiles_reported_available"])
        self.assertEqual(row["source_native_id"], "")

    def test_reference_and_link_tables_are_not_read_or_added_as_candidates(self):
        self.write_csv("1,A,50-00-0,C=O,,KEY\n")
        for scope in ("identity_reference", "literature_links"):
            self.spec["sources"].append({"id": scope, "filename": scope + ".csv", "tables": [{
                "id": scope, "sheet": None, "header": 0, "required_columns": ["id"],
                "record_mapping": {"scope": scope}}]})
        result = self.build()
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.mapping), 3)
        self.assertEqual(len(result.manifest["input_files"]), 1)

    def test_missing_mapping_and_missing_declared_columns_fail(self):
        self.write_csv("1,A,50-00-0,C=O,,KEY\n")
        self.mapping["fields"]["smiles_reported"].append("Absent fallback")
        with self.assertRaisesRegex(ValueError, "Missing mapped columns"):
            self.build()
        del self.table["record_mapping"]
        with self.assertRaisesRegex(ValueError, "record scope"):
            self.build()

    def test_csv_positions_are_parsed_records_not_physical_line_numbers(self):
        self.write_csv('001,"Two\nlines",50-00-0,C=O,,KEY\n\n002,B,,,,\n')
        records = self.build().records
        self.assertEqual(records["source_record_number"].tolist(), [1, 2])
        self.assertTrue(records["source_row_number"].isna().all())
        self.assertEqual(records.iloc[0]["name_reported"], "Two\nlines")

    def test_excel_positions_include_header_offset_and_internal_empty_rows(self):
        self.path = self.source_dir / "inventory.xlsx"
        self.spec["sources"][0]["filename"] = self.path.name
        self.table.update(sheet="Records", header=2)
        self.mapping["required_for_inclusion"] = ["inchikey_reported"]
        frame = pd.DataFrame({"local_id": ["001", "", "003"], "Name": ["A", "", "C"],
                              "CAS": ["", "", ""], "Isomeric": ["C", "", "C"],
                              "Canonical": ["", "", ""], "Key": ["K1", "", "K3"]})
        frame.to_excel(self.path, sheet_name="Records", startrow=2, index=False)
        records = self.build().records
        self.assertEqual(records["source_row_number"].tolist(), [4, 5, 6])
        self.assertEqual(records["source_record_number"].tolist(), [1, 2, 3])
        self.assertEqual(records["included"].tolist(), [True, False, True])

    def test_written_records_and_manifest_preserve_exclusions_and_fingerprints(self):
        self.mapping["required_for_inclusion"] = ["inchikey_reported"]
        self.write_csv("001,A,50-00-0,C=O,,NA\n")
        result = self.build()
        output = self.root / "output"
        result.write_reports(output)
        saved = pd.read_csv(output / "source_records.csv", dtype=str, keep_default_na=False)
        self.assertEqual(saved.iloc[0]["source_native_id"], "001")
        self.assertEqual(saved.iloc[0]["included"], "False")
        self.assertEqual(json.loads(saved.iloc[0]["reported_fields_json"])["Key"], "NA")
        manifest = json.loads((output / "source_record_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["input_files"][0]["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(manifest["catalog_sha256"], hashlib.sha256(self.catalog.read_bytes()).hexdigest())
        for name, digest in manifest["output_sha256"].items():
            self.assertEqual(digest, hashlib.sha256((output / name).read_bytes()).hexdigest())

    def test_source_mutation_during_read_is_rejected(self):
        self.write_csv("001,A,50-00-0,C=O,,KEY\n")
        from plastprior.inputs import _read_table

        def changing_reader(path, table):
            frame = _read_table(path, table)
            path.write_text(path.read_text(encoding="utf-8") + "002,B,,,,\n", encoding="utf-8")
            return frame

        with patch("plastprior.inputs._read_table", side_effect=changing_reader):
            with self.assertRaisesRegex(ValueError, "Source changed"):
                self.build()


if __name__ == "__main__":
    unittest.main()
