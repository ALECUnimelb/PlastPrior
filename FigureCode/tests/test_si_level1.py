"""Scientific refresh cases without editing the formal data or annotations."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import importlib.util
import json
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('si_prepare_test',ROOT/'FigureCode/Supplementary/SILevel1Evidence/prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
CONFIG=json.loads((ROOT/'result/figure_data/_metadata/scoring_config.json').read_text())
POLICY=json.loads((ROOT/'FigureCode/_shared/five_level_policy.json').read_text())


def record(key='one',config=None,**overrides):
    config=config or CONFIG
    row={'inchikey':key,'Name':'Example '+key,'CAS':'001-02-3','Priority_level':'1',
         'Priority_rank':'7','GIC_regulatory_status':'prohibited_or_phaseout'}
    row.update({field:'1' if label in ['FC','HB'] else '2' for label,field,_,_ in p.COMPONENTS})
    row.update(overrides)
    for domain in ['hazard','exposure']:
        total=sum(Decimal(row[field] or 0)*Decimal(str(weight)) for field,weight in config[f'{domain}_weights'].items())
        row[f'{domain.title()}_score_raw']=str(total)
        row[f'{domain.title()}_score']=str(total.quantize(Decimal(1),rounding=ROUND_HALF_UP))
    row['Priority_score']=str(int(row['Hazard_score'])+int(row['Exposure_score']))
    return row


class SIRefreshTests(unittest.TestCase):
    def test_new_members_preserved_without_annotations(self):
        rows,_,_,changes=p.prepare_rows([record('one'),record('two')],[{'inchikey':'one','primary_use':'Solvent'}],CONFIG,POLICY)
        self.assertEqual(len(rows),2)
        self.assertEqual(changes['unclassified'],['two'])
        self.assertEqual(rows[1]['annotation_status'],'Pending classification')
        self.assertEqual([r['Priority_rank'] for r in rows],[7,7])

    def test_source_four_level_one_does_not_define_the_si_cohort(self):
        low=record('source_level_one',Persistence_score='1',Mobility_score='0',Bioaccumulation_score='0')
        rows,_,levels,_=p.prepare_rows([low,record('dual_vh')],[],CONFIG,POLICY)
        self.assertEqual([r['inchikey'] for r in rows],['dual_vh'])
        self.assertEqual(levels,{1:1,2:1})

    def test_quarter_points_and_half_up_raw_totals_are_retained(self):
        row=record(Persistence_score='0.25')
        rows,_,_,_=p.prepare_rows([row],[],CONFIG,POLICY)
        self.assertEqual(rows[0]['Persistence_score'],.25)
        self.assertEqual(rows[0]['Hazard_score_raw'],12.5)
        self.assertEqual(rows[0]['Hazard_score'],13)

    def test_missing_and_supported_zero_remain_distinct(self):
        rows,_,_,_=p.prepare_rows([record('missing',Bioaccumulation_score=''),record('zero',Bioaccumulation_score='0')],[],CONFIG,POLICY)
        bykey={r['inchikey']:r for r in rows}
        self.assertIsNone(bykey['missing']['Bioaccumulation_score'])
        self.assertEqual(bykey['zero']['Bioaccumulation_score'],0)
        self.assertIn('B',bykey['missing']['missing_components'])
        self.assertEqual(bykey['zero']['missing_components'],'')

    def test_updated_weights_come_from_the_selected_run(self):
        config=deepcopy(CONFIG);config['exposure_weights']['Exposure_inventory_score']=1;config['exposure_weights']['Exposure_patent_score']=3
        rows,components,_,_=p.prepare_rows([record(config=config)],[],config,POLICY)
        weights={c['abbreviation']:c['weight'] for c in components}
        self.assertEqual((weights['Inv'],weights['Pat']),(1,3))
        self.assertEqual(rows[0]['Exposure_score'],14)

    def test_duplicate_annotation_keys_fail(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            p.prepare_rows([record()],[{'inchikey':'one'},{'inchikey':'one'}],CONFIG,POLICY)

    def test_identity_label_changes_are_reported(self):
        rows,_,_,changes=p.prepare_rows([record()],[{'inchikey':'one','Name':'Earlier name','primary_use':'Solvent'}],CONFIG,POLICY)
        self.assertEqual(rows[0]['Name'],'Example one')
        self.assertEqual(rows[0]['annotation_status'],'Identity labels need review')
        self.assertEqual(len(changes['issues']),1)

    def test_unlisted_gic_is_preserved_and_unknown_categories_fail(self):
        rows,_,_,_=p.prepare_rows([record(GIC_regulatory_status='not_listed')],[],CONFIG,POLICY)
        self.assertEqual(rows[0]['Regulatory_code'],'N')
        with self.assertRaisesRegex(ValueError,'Unmapped GIC'):
            p.prepare_rows([record(GIC_regulatory_status='new_unreviewed_category')],[],CONFIG,POLICY)

    def test_inconsistent_scores_fail_without_silent_rescoring(self):
        row=record();row['Hazard_score']='15'
        with self.assertRaisesRegex(ValueError,'rounded scores'):
            p.prepare_rows([row],[],CONFIG,POLICY)

    def test_unranked_nonmembers_do_not_block_refresh(self):
        low=record('unranked',Persistence_score='0',Mobility_score='0',Bioaccumulation_score='0',Toxicity_score='0',Priority_rank='')
        rows,_,_,_=p.prepare_rows([low,record('ranked')],[],CONFIG,POLICY)
        self.assertEqual([r['inchikey'] for r in rows],['ranked'])
        with self.assertRaisesRegex(ValueError,'competition rank'):
            p.prepare_rows([record(Priority_rank='')],[],CONFIG,POLICY)


if __name__=='__main__':unittest.main()
