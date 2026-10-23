"""Test specialist source matching, counting, provenance and model exclusion boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.evidence_specialists import (
    POLICY, build_cas_view, build_litchemplast_indexes, resolve_litchemplast_for_row,
    build_fcchumon_indexes, resolve_fcchumon_for_row, S1_DETECTION_COLUMN,
    S2_DETECTION_COLUMN, S2_DATABASE_DETECTION_COLUMN, _conversion_audit,
    _trace_indexes, _candidate_trace, _load_specialist_tables, require_prediction_isolation)
from plastprior.lrtp import VALUE_COLUMNS

KEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
OTHER = "OKKJLVBELUTLKV-UHFFFAOYSA-N"
CAS = "64-17-5"


class SpecialistTests(unittest.TestCase):
    def chemical(self, rows):
        return pd.DataFrame(rows, columns=["Chem_id", "INCHIKEY", "CASRN", "count_LitChem_id"])

    def links(self, rows):
        return pd.DataFrame(rows, columns=["Chem_id", "LitChem_id", "Lit_id"])

    def target(self, key=KEY, aliases=None, status="one_to_one"):
        return pd.Series({"Inchikey_std": key, "CAS": CAS,
                          "cas_values_json": json.dumps(aliases if aliases is not None else [CAS]),
                          "cas_mapping_status": status})

    def human(self, s1=None, s2=None):
        return build_fcchumon_indexes(
            pd.DataFrame(s1 or [], columns=["CAS", "Chemical name", S1_DETECTION_COLUMN]),
            pd.DataFrame(s2 or [], columns=["CAS", "Chemical name", S2_DETECTION_COLUMN, S2_DATABASE_DETECTION_COLUMN]))

    def test_exact_key_precedes_cas_and_counts_distinct_links_and_publications(self):
        index = build_litchemplast_indexes(self.chemical([[1,KEY,CAS,100],[2,KEY,CAS,30],[3,None,CAS,999]]),
            self.links([[1,10,1],[1,10,1],[2,11,1],[2,12,2],[3,13,3]]))
        result = resolve_litchemplast_for_row(self.target(status="multiple_connectivity_conflict"),index)
        self.assertEqual(result["match_method"],"exact_full_inchikey")
        self.assertEqual(result["linked_record_count"],3)
        self.assertEqual(result["unique_publication_count"],2)
        self.assertEqual(result["declared_count_max"],100)
        self.assertEqual(result["chem_ids"],"1|2")

    def test_conflicting_valid_source_key_cannot_be_used_as_cas_fallback(self):
        index = build_litchemplast_indexes(self.chemical([[1,OTHER,CAS,1]]),self.links([[1,10,1]]))
        result = resolve_litchemplast_for_row(self.target(),index)
        self.assertFalse(result["selected"])
        self.assertEqual(result["match_method"],"no_match")

    def test_cas_fallback_requires_one_candidate_and_unambiguous_target(self):
        index = build_litchemplast_indexes(self.chemical([[1,None,CAS,1],[2,"invalid","67-56-1",1]]),self.links([[1,10,1],[2,11,2]]))
        self.assertEqual(resolve_litchemplast_for_row(self.target(),index)["match_method"],"cas_fallback_source_inchikey_missing")
        self.assertEqual(resolve_litchemplast_for_row(self.target(status="same_connectivity_multiple_full_inchikeys"),index)["match_method"],"cas_rejected_ambiguous_target_mapping")
        self.assertEqual(resolve_litchemplast_for_row(self.target(aliases=[CAS,"67-56-1"]),index)["match_method"],"cas_rejected_multiple_source_candidates")

    def test_zero_link_count_is_a_selected_source_and_does_not_use_declared_count(self):
        index = build_litchemplast_indexes(self.chemical([[1,KEY,CAS,77]]),self.links([]))
        result=resolve_litchemplast_for_row(self.target(),index)
        self.assertTrue(result["selected"])
        self.assertEqual(result["linked_record_count"],0)
        self.assertEqual(result["count_source"],"unique_LiteratureChemical.LitChem_id")

    def test_fcchumon_takes_maximum_within_sheet_without_summing(self):
        index=self.human([[CAS,"Ethanol",2],[CAS,"Ethanol",5]])
        result=resolve_fcchumon_for_row(self.target(),index)
        self.assertEqual(result["detection_count"],5)
        self.assertEqual(result["source_row_count"],2)
        self.assertTrue(result["detected"])

    def test_fcchumon_s2_uses_study_count_separately_from_database_count(self):
        result=resolve_fcchumon_for_row(self.target(),self.human(s2=[[CAS,"Ethanol",0,9]]))
        self.assertTrue(result["selected"])
        self.assertFalse(result["detected"])
        self.assertEqual(result["database_detection_count"],9)
        self.assertEqual(result["detection_field"],S2_DETECTION_COLUMN)

    def test_fcchumon_rejects_cross_sheet_and_target_cas_ambiguity(self):
        index=self.human([[CAS,"Ethanol",2]],[[CAS,"Ethanol",3,5]])
        self.assertEqual(resolve_fcchumon_for_row(self.target(),index)["match_method"],"cas_rejected_multiple_source_candidates")
        self.assertEqual(resolve_fcchumon_for_row(self.target(status="multiple_connectivity_conflict"),index)["match_method"],"cas_rejected_ambiguous_target_mapping")

    def test_missing_invalid_and_fractional_counts_keep_conversion_reasons(self):
        rows=[{"record_id":str(i),"table_id":"fcchumon_s1","raw_fields":{S1_DETECTION_COLUMN:v}}
              for i,v in enumerate([None,"unknown",0,1.9])]
        audit=_conversion_audit(rows)
        self.assertEqual([r["normalized_value"] for r in audit],[0,0,0,1])
        self.assertEqual([r["conversion_reason"] for r in audit],["missing_to_zero_historical_rule","nonnumeric_to_zero_historical_rule","preserved_numeric_value","fractional_value_truncated_historical_rule"])
        with self.assertRaisesRegex(ValueError,"non-negative"):
            _conversion_audit([{"record_id":"bad","table_id":"fcchumon_s1","raw_fields":{S1_DETECTION_COLUMN:-1}}])
        with self.assertRaisesRegex(ValueError,"non-negative"):
            build_litchemplast_indexes(self.chemical([[1,KEY,CAS,-1]]),self.links([]))

    def test_cas_projection_uses_all_members_and_worst_alias_status(self):
        compounds=pd.DataFrame([{"inchikey":KEY,"cas_reported":CAS}])
        members=pd.DataFrame([{"inchikey":KEY,"record_id":r} for r in ["one","two"]])
        records=pd.DataFrame([{"record_id":"one","cas_reported":CAS,"source_sha256":"hash"},
                              {"record_id":"two","cas_reported":"67-56-1","source_sha256":"hash"}])
        audit=pd.DataFrame([{"cas":c,"mapping_status":status,"inchikey_count":len(keys),"connectivity_count":len(keys),
                             "inchikeys_json":json.dumps(keys),"connectivity_keys_json":json.dumps([k[:14] for k in keys])}
                            for c,status,keys in [(CAS,"one_to_one",[KEY]),("67-56-1","multiple_connectivity_conflict",[KEY,OTHER])]])
        view,links=build_cas_view(compounds,members,records,audit)
        self.assertEqual(json.loads(view.iloc[0]["cas_values_json"]),[CAS,"67-56-1"])
        self.assertEqual(view.iloc[0]["cas_mapping_status"],"multiple_connectivity_conflict")
        self.assertEqual(set(links["record_id"]),{"one","two"})
        self.assertEqual(compounds.iloc[0]["cas_reported"],CAS)

    def test_relationship_trace_retains_duplicates_without_recounting(self):
        chemical=self.chemical([[1,KEY,CAS,3]])
        links=self.links([[1,10,1],[1,10,1],[1,11,1]])
        source=[]
        for table,frame in [("litchemplast",chemical),("litchemplast_links",links)]:
            for i,raw in enumerate(frame.to_dict("records"),1):
                source.append({"record_id":table+str(i),"table_id":table,"source_record_number":i,"raw_fields":raw})
        index=_trace_indexes({},source)
        lit=resolve_litchemplast_for_row(self.target(),build_litchemplast_indexes(chemical,links))
        human=resolve_fcchumon_for_row(self.target(),self.human())
        candidates,decisions=_candidate_trace(KEY,[CAS],lit,human,index)
        self.assertEqual(len(decisions),3)
        self.assertEqual(sum(r["counted_link_record"] for r in decisions),2)
        self.assertEqual(sum(r["counted_publication"] for r in decisions),1)
        self.assertEqual(decisions[1]["link_reason"],"duplicate_identifier_not_recounted")
        self.assertEqual(candidates[0]["source_record_ids"],["litchemplast1"])

    def test_prediction_isolation_rejects_zero_and_false_as_values_for_review_rows(self):
        config=json.loads(Path('plastprior/qsar_models.json').read_text(encoding='utf-8'))
        fields=[c for c in config['legacy_merge_columns'] if not c.startswith('Basic | ')]
        frame=pd.DataFrame([{**{c:"" for c in fields+VALUE_COLUMNS},"qsar_identity_status":"review_required",
                             "qsar_evidence_available":"False","lrtp_available":"False"}])
        require_prediction_isolation(frame)
        for column,value in [(fields[0],"0"),(VALUE_COLUMNS[-1],"False"),("qsar_evidence_available","True")]:
            changed=frame.copy();changed.loc[0,column]=value
            with self.assertRaisesRegex(ValueError,"bypassed"):
                require_prediction_isolation(changed)

    def test_changed_workbook_fails_before_reading(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'SourceDatabase').mkdir()
            (root/'SourceDatabase'/'source.xls').write_bytes(b'changed bytes')
            catalog={'sources':[{'id':'source','filename':'source.xls','tables':[{'id':'litchemplast'}]}]}
            records=pd.DataFrame(columns=['table_id','source_record_number'])
            with patch('plastprior.evidence_specialists.load_catalog',return_value=catalog),patch('plastprior.evidence_specialists.pd.read_excel') as read:
                with self.assertRaisesRegex(ValueError,'differs from Stage 4A'):
                    _load_specialist_tables(root,records,{'source.xls':'old hash'})
                read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
