"""Exercise identity policy boundaries independently of the research collection."""

from functools import lru_cache
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.identity import (_aggregate, _cas_audit, _load_references, _lookups,
                                 _resolve_row, _standardize, IdentityResult, resolve_identities)
from plastprior.inputs import _file_hash, load_catalog, SourceRecords


def record(number="1", **changes):
    return {"record_id": number, "table_id": "example", "source_record_number": int(number),
            "included": True, "name_reported": "Example", "cas_reported": "",
            "smiles_reported": "", "inchikey_reported": "", **changes}


def reference(number, smiles, **changes):
    structure = _standardize(smiles) if smiles else None
    return {"reference_id": str(number), "reference_table": "plastchem",
            "reference_record_number": number, "reference_native_id": str(number),
            "name": "Reference", "cas": "", "smiles": smiles,
            "inchikey": structure["inchikey"] if structure else "", **changes}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.standardize = lru_cache(maxsize=None)(_standardize)
        self.empty = {name: {} for name in ("pubchemlite", "plastchem", "norman_susdat")}

    def resolve(self, row, keys=None, unique=None, ambiguous=None):
        return _resolve_row(row, keys or self.empty, unique or {}, ambiguous or {}, self.standardize)

    def tables(self, plast=None, pub=None, norman=None):
        columns = list(reference(1, "C"))
        return {"plastchem": pd.DataFrame(plast or [], columns=columns),
                "pubchemlite": pd.DataFrame(pub or [], columns=columns),
                "norman_susdat": pd.DataFrame(norman or [], columns=columns)}

    def test_stereoisomers_remain_distinct_while_qsar_keys_can_coincide(self):
        first = self.resolve(record(smiles_reported="N[C@@H](C)C(=O)O"))
        second = self.resolve(record(smiles_reported="N[C@H](C)C(=O)O"))
        self.assertNotEqual(first["inchikey"], second["inchikey"])
        self.assertEqual(first["connectivity_key"], second["connectivity_key"])
        self.assertEqual(first["qsar_inchikey"], second["qsar_inchikey"])
        self.assertEqual(first["stereo_status"], "specified")

    def test_reported_structure_precedes_conflicting_reported_key(self):
        result = self.resolve(record(smiles_reported="CCO", inchikey_reported=_standardize("C")["inchikey"]))
        self.assertEqual(result["resolution_route"], "reported_smile")
        self.assertEqual(result["reported_derived_status"], "different_connectivity")
        self.assertTrue(result["aggregation_eligible"])

    def test_key_lookup_priority_and_multicomponent_reference_policy(self):
        hit = reference(1, "[Na+].[Cl-]", reference_table="pubchemlite")
        keys = {**self.empty, "pubchemlite": {hit["inchikey"]: hit}}
        result = self.resolve(record(smiles_reported=hit["smiles"], inchikey_reported=hit["inchikey"]), keys)
        self.assertEqual(result["reported_smiles_status"], "rejected_multicomponent_or_wildcard")
        self.assertEqual(result["resolution_route"], "pubchemlite_inchikey")
        self.assertEqual(result["selected_reference_id"], "1")
        self.assertTrue(result["aggregation_eligible"])

    def test_duplicate_reference_keys_keep_first_row_and_audit_alternatives(self):
        key = _standardize("CCO")["inchikey"]
        tables = self.tables(plast=[reference(1, "", inchikey=key), reference(2, "CCO")])
        keys, unique, ambiguous, audit = _lookups(tables, self.standardize)
        result = self.resolve(record(inchikey_reported=key), keys, unique, ambiguous)
        self.assertEqual(result["resolution_route"], "unresolved")
        self.assertEqual(audit.iloc[0]["issue"], "duplicate_reference_inchikey")
        self.assertEqual(len(json.loads(audit.iloc[0]["candidates_json"])), 2)

    def test_cas_agreement_requires_full_keys_and_rejects_reported_mismatch(self):
        tables = self.tables(plast=[reference(1, "N[C@@H](C)C(=O)O", cas="56-41-7"),
                                    reference(2, "N[C@H](C)C(=O)O", cas="56-41-7")])
        keys, unique, ambiguous, _ = _lookups(tables, self.standardize)
        result = self.resolve(record(cas_reported="56-41-7"), keys, unique, ambiguous)
        self.assertFalse(result["aggregation_eligible"])
        self.assertEqual(json.loads(result["attempts_json"])[-1]["outcome"], "ambiguous_full_keys")
        hit = reference(3, "CCO", cas="64-17-5")
        result = self.resolve(record(cas_reported="64-17-5", inchikey_reported=_standardize("C")["inchikey"]),
                              unique={"64-17-5": hit})
        self.assertEqual(result["resolution_route"], "unresolved")
        self.assertEqual(json.loads(result["attempts_json"])[-1]["outcome"], "reported_key_mismatch")

    def test_unambiguous_cas_prefers_plastchem_and_ignores_invalid_candidates(self):
        tables = self.tables(plast=[reference(1, "CCO", cas="64-17-5"),
                                    reference(2, "", cas="64-17-5")],
                             norman=[reference(3, "CCO", cas="64-17-5", reference_table="norman_susdat")])
        keys, unique, ambiguous, _ = _lookups(tables, self.standardize)
        result = self.resolve(record(cas_reported=" '64-17-5 "), keys, unique, ambiguous)
        self.assertEqual(result["resolution_route"], "plastchem_cas")
        self.assertEqual(result["selected_reference_id"], "1")

    def test_parse_success_without_key_is_retained_but_never_aggregated(self):
        structure = {**_standardize("CCO"), "inchikey": "", "connectivity_key": "", "qsar_inchikey": ""}
        with patch("plastprior.identity.inchi.MolToInchiKey", return_value=""):
            result = _resolve_row(record(smiles_reported="CCO"), self.empty, {}, {}, _standardize)
        self.assertEqual(result["resolution_route"], "reported_smile")
        self.assertEqual(result["structure_parse_status"], "parsed")
        self.assertEqual(result["identity_key_status"], "missing")
        self.assertEqual(result["reported_derived_status"], "derived_key_unavailable")
        self.assertFalse(result["aggregation_eligible"])
        self.assertEqual(result["smiles_standard"], structure["smiles_standard"])

    def test_excluded_and_unresolved_records_are_distinct(self):
        excluded = self.resolve(record(included=False, smiles_reported="CCO"))
        unresolved = self.resolve(record(smiles_reported="not_a_structure"))
        self.assertEqual(excluded["resolution_route"], "excluded")
        self.assertEqual(unresolved["resolution_route"], "unresolved")
        self.assertEqual(unresolved["reported_smiles_status"], "invalid")
        self.assertFalse(excluded["aggregation_eligible"])

    def test_member_multiplicity_tier_order_and_cas_conflicts(self):
        rows = []
        for number, smiles, tier in (("1", "CCO", "D"), ("2", "CCO", "A"), ("3", "CCO", "A"), ("4", "CO", "A")):
            raw = record(number, smiles_reported=smiles, cas_reported="64-17-5; 64-17-6")
            rows.append({**raw, **self.resolve(raw), "route_tier": tier})
        compounds, members = _aggregate(pd.DataFrame(rows))
        ethanol = compounds.loc[compounds["n_records"].eq(3)].iloc[0]
        self.assertEqual(ethanol["representative_record_id"], "2")
        self.assertEqual(len(members), 4)
        self.assertEqual(members["record_id"].nunique(), 4)
        audit = _cas_audit(pd.DataFrame(rows))
        self.assertEqual(audit["cas"].tolist(), ["64-17-5"])
        self.assertEqual(audit.iloc[0]["mapping_status"], "multiple_connectivity_conflict")
        self.assertEqual(audit.iloc[0]["source_record_count"], 4)

    def test_empty_aggregation_has_a_readable_schema(self):
        raw = record()
        compounds, members = _aggregate(pd.DataFrame([{**raw, **self.resolve(raw)}]))
        self.assertTrue(compounds.empty)
        self.assertIn("inchikey", compounds.columns)
        self.assertIn("record_id", members.columns)

    def test_reference_mapping_and_mutation_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SourceDatabase").mkdir()
            sources = []
            for name in self.empty:
                pd.DataFrame({"ID": ["001", "002"], "Key": ["K", ""], "SMILES": ["C", "O"],
                              "Name": [" N ", "NA"], "CAS": ["", ""]}).to_csv(
                    root / "SourceDatabase" / (name + ".csv"), index=False, encoding="utf-8")
                sources.append({"id": name, "filename": name + ".csv", "tables": [{
                    "id": name, "header": 0, "sheet": None, "required_columns": ["ID"],
                    "identity_reference_mapping": {"native_id_column": "ID", "require_inchikey": name == "norman_susdat",
                                                   "fields": {"name": "Name", "cas": "CAS", "smiles": "SMILES", "inchikey": "Key"}}}]})
            catalog = root / "sources.json"
            catalog.write_text(json.dumps({"schema_version": 1, "sources": sources,
                                           "record_assembly_policy": {"missing_tokens": ["", "NA"]}}), encoding="utf-8")
            tables, manifests, summary = _load_references(root, catalog, load_catalog(catalog))
            self.assertEqual(len(tables["norman_susdat"]), 1)
            self.assertEqual(tables["plastchem"].iloc[0]["reference_native_id"], "001")
            self.assertEqual(tables["plastchem"]["name"].tolist(), ["N", ""])
            self.assertEqual(len(manifests), 3)
            with patch("plastprior.identity._file_hash", side_effect=["before", "after"]):
                with self.assertRaisesRegex(ValueError, "changed while reading"):
                    _load_references(root, catalog, load_catalog(catalog))

    def test_report_fingerprints(self):
        raw = record(smiles_reported="CCO")
        records = pd.DataFrame([{**raw, **self.resolve(raw)}])
        compounds, members = _aggregate(records)
        empty = pd.DataFrame(columns=["issue"])
        result = IdentityResult(records, compounds, members, _cas_audit(records), empty, empty, empty, {"test": True})
        with tempfile.TemporaryDirectory() as directory:
            result.write_reports(directory)
            root = Path(directory)
            manifest = json.loads((root / "identity_manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["output_sha256"].items():
                self.assertEqual(_file_hash(root / name), digest)

    def test_shared_inventory_reference_file_cannot_change_between_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "sources.json"
            catalog.write_text(json.dumps({"schema_version": 1, "sources": [{"id": "example",
                "filename": "shared.csv", "tables": [{"id": "example", "header": 0,
                "required_columns": ["Name"]}]}]}), encoding="utf-8")
            records = SourceRecords(pd.DataFrame([record(smiles_reported="CCO")]), pd.DataFrame(),
                pd.DataFrame([{"table_id": "example", "scope": "candidate_inventory"}]),
                {"catalog_sha256": _file_hash(catalog),
                 "input_files": [{"filename": "shared.csv", "sha256": "inventory-version"}]})
            references = (self.tables(), [{"filename": "shared.csv", "sha256": "reference-version"}], pd.DataFrame())
            with patch("plastprior.identity._load_references", return_value=references):
                with self.assertRaisesRegex(ValueError, "Inventory and reference fingerprints differ"):
                    resolve_identities(records, directory, catalog_path=catalog)


if __name__ == "__main__":
    unittest.main()
