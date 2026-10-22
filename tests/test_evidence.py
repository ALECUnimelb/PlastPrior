"""Verify basic source selection, historical boundaries and prediction isolation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.evidence import (DEFAULT_FIELDS, _best_column, _classification_decisions,
    _load_tables, isolate_predictions)
from plastprior._evidence_rules import unify_compound_record, iter_audit_rows, make_slim_record
from plastprior.lrtp import VALUE_COLUMNS
from plastprior.validation import _basic_historical_projection, _semantic_digest


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(DEFAULT_FIELDS.read_text(encoding="utf-8"))

    def match(self, row, index=0, kind="inchikey", value="KEY"):
        return {"row_index": index, "match_type": kind, "match_col": "InChIKey" if kind == "inchikey" else "CAS",
                "match_value": value, "data": row}

    def test_source_priority_and_all_identity_candidates_are_audited(self):
        bundle = {"per_db": {
            "UNEP": {"matches": [self.match({"InChIKey":"KEY", "Name":"secondary"})]},
            "PlastChem": {"matches": [self.match({"inchikey":"KEY", "Name":"preferred"})]}}}
        result = unify_compound_record(bundle)
        self.assertEqual(result["identity"]["name"], "preferred")
        entries = result["audit_trail"]["identity.name"]
        self.assertEqual([e["selected"] for e in entries], [True, False])
        self.assertEqual([e["db"] for e in entries], ["PlastChem", "UNEP"])

    def test_strict_cas_rejects_mismatch_but_retains_reason(self):
        bundle = {"identity": {"inchikey":"KEY", "cas":"64-17-5"}, "per_db": {
            "UNEP": {"matches":[self.match({"CAS":"67-56-1", "Name":"wrong"}, kind="cas", value="67-56-1")]}}}
        result=unify_compound_record(bundle)
        self.assertEqual(result["identity"]["inchikey"], "KEY")
        self.assertIsNone(result["identity"]["name"])
        events=list(iter_audit_rows(result,compound_key="CANONICAL"))
        self.assertEqual(events[0]["status"],"mismatch")
        self.assertIn("!= identity.cas",events[0]["reason"])
        self.assertEqual(events[0]["compound_key"],"CANONICAL")

    def test_duplicate_observations_preserve_audit_multiplicity_without_new_scores(self):
        match=self.match({"inchikey":"KEY", "Hazard_score":4})
        result=unify_compound_record({"per_db":{"PlastChem":{"matches":[match,match]}}})
        events=[e for e in iter_audit_rows(result,compound_key="KEY") if e["source_col"]=="Hazard_score"]
        self.assertEqual(len(events),2)
        field=events[0]["field_path"].split(".")
        value=make_slim_record(result)
        for part in field:value=value[part]
        self.assertEqual(value,{"PlastChem":[4]})
        self.assertNotIn("priority_score",result)

    def test_index_alias_resolution_and_missing_columns_are_explicit(self):
        self.assertEqual(_best_column(["InChIKey", "InChI Key"], ["InChIKey"]),"InChI Key")
        self.assertIsNone(_best_column(["Name"],["CAS"]))

    def test_classification_last_valid_row_and_nonpositive_flags_are_audited(self):
        column=self.config["field_rules"]["plastchem_polymer_columns"][0]
        matches=[self.match({"inchikey":"KEY", column:1, "Red_list":1},0), self.match({"inchikey":"KEY", column:2, "Red_list":0},1)]
        bundle={"per_db":{"PlastChem":{"matches":matches}}}
        provenance={("PlastChem",i):{"record_id":f"row-{i}","source_sha256":"frozen"} for i in range(2)}
        audit=_classification_decisions(bundle,{},self.config,"KEY",provenance)
        polymer=[e for e in audit if e["source_column"]==column]
        self.assertEqual([e["selection_reason"] for e in polymer], ["superseded_by_later_valid_row","selected_last_valid_row"])
        red=[e for e in audit if e["source_column"]=="Red_list"]
        self.assertEqual([e["selected"] for e in red],[True,False])
        self.assertEqual(red[1]["selection_reason"],"not_selected_nonpositive_list_annotation")
        result=unify_compound_record(bundle)
        self.assertEqual(result["classification"]["plastchem"]["polymer_context"][column],2)
        self.assertEqual(result["classification"]["plastchem"]["concern"]["Red_list"],1)

    def test_historical_all_zero_classification_block_is_audited_as_omitted(self):
        column=self.config["field_rules"]["plastchem_polymer_columns"][0]
        bundle={"per_db":{"PlastChem":{"matches":[self.match({"inchikey":"KEY",column:0})]}}}
        provenance={("PlastChem",0):{"record_id":"row-0","source_sha256":"frozen"}}
        audit=_classification_decisions(bundle,{},self.config,"KEY",provenance)
        event=next(e for e in audit if e["source_column"]==column)
        self.assertFalse(event["selected"])
        self.assertEqual(event["selection_reason"],"omitted_all_zero_block_historical_rule")
        self.assertEqual(event["raw_value"],0)
        self.assertNotIn("polymer_context",unify_compound_record(bundle)["classification"].get("plastchem",{}))

    def fixture(self):
        return pd.DataFrame([
            {"inchikey":key,"qsar_inchikey":key,"vega_row_no":str(i),
             "qsar_identity_status":status,"qsar_identity_verified":str(status=="exact_key_match"),
             "qsar_identity_reason":"representation_difference" if i==2 else "",
             "prediction":"0", "source_fact":"independent observation", "lrtp_available":str(i==1),
             **{c:"" if i==2 else "0" for c in VALUE_COLUMNS}}
            for i,key,status in [(1,"verified","exact_key_match"),(2,"review","review_required")]])

    def test_isolation_preserves_other_compounds_and_independent_evidence(self):
        original=self.fixture();output,audit=isolate_predictions(original,{"legacy_merge_columns":["prediction"]})
        self.assertEqual(original.loc[1,"prediction"],"0")
        self.assertEqual(output.loc[1,"prediction"],"")
        self.assertEqual(output.loc[0,"prediction"],"0")
        self.assertEqual(output.loc[1,"source_fact"],"independent observation")
        self.assertFalse(output.loc[1,"qsar_evidence_available"])
        self.assertEqual(len(audit),13)
        self.assertEqual(set(audit["exclusion_reason"]),{"identity_review_required"})

    def test_isolation_rejects_historical_scenarios_or_unmasked_lrtp(self):
        frame=self.fixture();frame["LRTP_evidence"]="{}"
        with self.assertRaisesRegex(ValueError,"Historical LRTP"):isolate_predictions(frame,{"legacy_merge_columns":["prediction"]})
        frame=self.fixture();frame.loc[1,VALUE_COLUMNS[0]]="0"
        with self.assertRaisesRegex(ValueError,"has not isolated"):isolate_predictions(frame,{"legacy_merge_columns":["prediction"]})

    def test_baseline_projection_restores_only_generic_literature(self):
        old={"litchemplast_resolution":{"count":99},"fcchumon_resolution":{},"analytical_detectability":{},
             "exposure":{"literature":{"litchemplast_count":{"LitChemPlast":[99]},"other":7}},"hazard":{"source_score":4}}
        projection=_basic_historical_projection(old,{"LitChemPlast":[3.0]})
        self.assertEqual(projection["exposure"]["literature"],{"litchemplast_count":{"LitChemPlast":[3.0]},"other":7})
        self.assertEqual(old["exposure"]["literature"]["litchemplast_count"],{"LitChemPlast":[99]})
        self.assertEqual(projection["hazard"],old["hazard"])
        self.assertNotIn("fcchumon_resolution",projection)

    def test_audit_comparison_retains_types_and_list_order(self):
        self.assertEqual(_semantic_digest({"a":1.0,"b":[2]}),_semantic_digest({"b":[2.0],"a":1}))
        for a,b in [(False,0),(None,""),([1,2],[2,1]),(1,1.000000001)]:
            self.assertNotEqual(_semantic_digest(a),_semantic_digest(b))

    def test_changed_input_hash_fails_before_reading_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"SourceDatabase").mkdir()
            (root/"SourceDatabase"/"sample.csv").write_text("CAS\n64-17-5\n",encoding="utf-8")
            catalog={"sources":[{"id":"sample","filename":"sample.csv","tables":[{"id":"sample","header":0,"sheet":None}]}]}
            records=pd.DataFrame([{"table_id":"sample","source_sha256":"wrong"}])
            with patch("plastprior.evidence.pd.read_csv") as read:
                with self.assertRaisesRegex(ValueError,"does not match Stage 2"):
                    _load_tables(root,catalog,{"source_labels":{"Sample":"sample"}},records)
                read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
