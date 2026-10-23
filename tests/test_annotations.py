"""Test annotation selection, source provenance and unresolved identity boundaries."""
import unittest
import tempfile
from collections import defaultdict
from pathlib import Path
import json
from unittest.mock import patch

import pandas as pd

from plastprior.evidence_annotations import (
    POLICY, NORMAN_SUSDAT_KEY_COLUMNS, NORMAN_ANALYTICAL_COLUMNS, build_norman_lookup,
    build_cid_bridges, resolve_gic, _listing_record, _derive_regulatory_action_class,
    dependency_fingerprint, source_record, trace_gic_sources)

KEY = 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N'
SOURCE = {'id': 'NORMAN_SusDat', 'table_id': 'norman_susdat', 'filename': 'test.xlsx',
          'sha256': 'test-hash', 'sheet': 'Sheet1'}


class Inventory:
    def __init__(self, identifiers, tags): self.identifiers, self.tags = identifiers, tags
    def get_by_identifiers(self, field, identifiers): return self.identifiers.get(identifiers[0], [])
    def get_by_sids(self, field, sids): return self.tags.get(sids[0], [])


class AnnotationTests(unittest.TestCase):
    def norman(self, values):
        return pd.DataFrame([{**dict.fromkeys(NORMAN_SUSDAT_KEY_COLUMNS + NORMAN_ANALYTICAL_COLUMNS),
                              'MS_Ready_StdInChIKey': KEY, 'Norman_SusDat_ID': str(i), **v}
                             for i, v in enumerate(values)])

    def test_norman_completeness_precedes_probability_and_preserves_zero(self):
        raw = self.norman([{'Prob. RPLC': 0.9}, {'Prob. RPLC': 0, 'Prob. ESI': 0}])
        lookup, audit = build_norman_lookup(raw, SOURCE)
        self.assertEqual(lookup[KEY]['evidence']['norman_susdat_id'], '1')
        self.assertEqual(lookup[KEY]['evidence']['derived_scores']['lc_esi'], 0)
        self.assertEqual(audit[0]['decision_reason'], 'lower_nonmissing_field_count')
        self.assertEqual(audit[1]['source_row_number'], 3)

    def test_norman_tie_and_invalid_numeric_are_audited(self):
        raw = self.norman([{'Prob. EI': 0.8, 'Prob. GC': 'bad'}, {'Prob. EI': 0.8}, {'MS_Ready_StdInChIKey': None}])
        raw.loc[0, 'Prob. of GC'] = 'invalid'
        lookup, audit = build_norman_lookup(raw, SOURCE)
        self.assertEqual(lookup[KEY]['evidence']['norman_susdat_id'], '0')
        self.assertEqual(audit[1]['decision_reason'], 'ranking_tie_first_source_row_retained')
        self.assertEqual(audit[2]['decision_reason'], 'missing_ms_ready_key')
        self.assertEqual(audit[0]['probability_conversions'][0]['reason'], 'non_numeric_coerced_to_missing')
        json.dumps(audit, allow_nan=False)

    def test_source_id_changes_with_source_bytes_and_preserves_physical_row(self):
        first = source_record(SOURCE, 3, {'Name': 'ethanol'})
        second = source_record({**SOURCE, 'sha256': 'different'}, 3, {'Name': 'ethanol'})
        self.assertNotEqual(first['record_id'], second['record_id'])
        self.assertEqual(first['source_row_number'], 4)

    def bridges(self): return {'pubchemlite': defaultdict(set), 'susdat': defaultdict(set)}

    def resolve(self, inventory, bridges=None, caps=None, name='ethanol'):
        return resolve_gic(KEY, name, inventory, {}, bridges or self.bridges(),
                           caps or {'inchikey': False, 'cid': True, 'chemical_name': True}, 0)

    def test_cid_union_preserves_both_sources_and_precedes_name(self):
        bridges = self.bridges(); bridges['pubchemlite'][KEY]={'CID1'}; bridges['susdat'][KEY]={'CID2'}
        fields, audit = self.resolve(Inventory({'CID1':[1], 'CID2':[2], 'ethanol':[3]}, {1:['AU-AIIC'],2:['CASCC'],3:['EU-SVHC']}), bridges)
        self.assertEqual(audit['match_method'], 'cid_bridge')
        self.assertEqual(audit['matched_sids'], [1,2])
        self.assertEqual(len(audit['lookup_attempts']), 1)
        self.assertEqual(audit['bridged_cids'], {'pubchemlite':['CID1'], 'susdat':['CID2']})

    def test_full_key_precedes_cid_bridge(self):
        fields, audit = self.resolve(Inventory({KEY:[1]}, {1:['AU-AIIC']}), caps={'inchikey':True,'cid':True,'chemical_name':True})
        self.assertEqual(audit['match_method'], 'inchikey')

    def test_auxiliary_cid_can_be_superseded_by_name(self):
        bridges=self.bridges(); bridges['pubchemlite'][KEY]={'CID1'}
        fields, audit=self.resolve(Inventory({'CID1':[1],'ethanol':[2]}, {1:['CASCC'],2:['AU-AIIC']}), bridges)
        self.assertEqual(audit['match_method'], 'chemical_name')
        self.assertEqual(len(audit['lookup_attempts']), 2)
        self.assertIn('matched_by_chemical_name_fallback', audit['caveats'])

    def test_auxiliary_fallback_is_retained_without_inflating_regulatory_count(self):
        bridges=self.bridges(); bridges['pubchemlite'][KEY]={'CID1'}
        fields, audit=self.resolve(Inventory({'CID1':[1]}, {1:['CASCC']}), bridges)
        self.assertEqual(audit['status'], 'auxiliary_identifier_only')
        self.assertEqual(audit['regulatory_listing_count'], 0)
        self.assertEqual(audit['match_method'], 'cid_bridge')

    def test_not_queried_and_no_match_are_distinct(self):
        _, unqueried=self.resolve(Inventory({},{}),name='')
        _, unmatched=self.resolve(Inventory({},{}))
        self.assertIsNone(unqueried['inventory_listing_count'])
        self.assertEqual(unqueried['inventory_data_status'],'not_queried')
        self.assertEqual(unmatched['inventory_listing_count'],0)
        self.assertEqual(unmatched['inventory_data_status'],'available')

    def test_metadata_classification_rationale_and_invalid_class(self):
        self.assertEqual(_derive_regulatory_action_class('unknown',''),('monitoring_reporting_or_hazard_classification','fallback_unknown_non_auxiliary'))
        self.assertEqual(_derive_regulatory_action_class('unknown','auxiliary')[0], 'auxiliary_identifier_only')
        with self.assertRaises(ValueError): _derive_regulatory_action_class('unknown','','invalid')

    def test_bridge_links_retain_both_susdat_key_paths_and_missing_cid_reason(self):
        pcl=pd.DataFrame([{'Identifier':1,'InChIKey':KEY,'Related_CIDs':'1;2'}, {'Identifier':2,'InChIKey':KEY,'Related_CIDs':None}])
        sus=pd.DataFrame([{'Norman_SusDat_ID':'NS1','StdInChIKey':KEY,'MS_Ready_StdInChIKey':KEY,'PubChem_CID':3}])
        bridges, links, rows=build_cid_bridges(pcl,sus,{'pubchemlite':{**SOURCE,'id':'PubChemLite'},'susdat':SOURCE},{KEY})
        self.assertEqual(bridges['pubchemlite'][KEY],{'CID1','CID2'})
        self.assertEqual(bridges['susdat'][KEY],{'CID3'})
        self.assertEqual(len(links),4)
        self.assertEqual(links[1]['decision_reason'],'missing_or_unparseable_cid')

    def test_shared_identifier_can_add_tags_from_an_unmatched_sid(self):
        from gic import Inventory as GICInventory
        records = [{'list_data': {'1': 'AU-AIIC', '2': 'EU-SVHC'}},
                   {'1': {'chemical_name': {'Shared name': [1]}, 'cid': {'CID1': [1]}}},
                   {'2': {'chemical_name': {'Shared name': [2]}, 'cid': {'CID2': [2]}}},
                   {'3': {'chemical_name': {'Unrelated name': [1]}, 'cid': {'CID3': [1]}}}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'inventory.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
            _, sources, support = trace_gic_sources(path, {1}, GICInventory(str(path)))
        self.assertEqual(sources[0]['local_list_tags'], ['AU-AIIC'])
        self.assertEqual(sources[0]['effective_list_tags'], ['AU-AIIC', 'EU-SVHC'])
        self.assertEqual(sources[0]['shared_identifier_added_tags'], ['EU-SVHC'])
        self.assertEqual({row['sid'] for row in support}, {1, 2})
        self.assertEqual({row['sid'] for row in sources}, {1})

    def test_wrong_same_named_dependency_is_rejected(self):
        with patch('plastprior.evidence_annotations.importlib.metadata.distribution') as dist:
            dist.return_value.version='0.0.0'; dist.return_value.read_text.return_value='{}'
            with self.assertRaisesRegex(ValueError,'PyPI'): dependency_fingerprint()


if __name__ == '__main__': unittest.main()
