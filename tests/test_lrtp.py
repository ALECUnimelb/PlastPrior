"""Test historical calculation boundaries and the exclusion of unverified identities."""

import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from plastprior.inputs import _file_hash
from plastprior.lrtp import (PARAMETERS, LRTP_REQUIRED_PREDICTION_COLUMNS, VALUE_COLUMNS,
    LRTP_OUTPUT_COLUMNS, _calculate_row_lrtp, _solve_linear_3x3, calculate_oecd_lrtp,
    derive_log_kaw_from_vp_and_solubility, integrate_lrtp)
from plastprior.validation import _compare_evidence, _compare_qsar_frame


class LRTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="PlastPrior LRTP ")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.properties = [5.88, 0.0475, 71.0, 708.0, -6.5999, 6.31]
        self.row = pd.Series(dict(zip(LRTP_REQUIRED_PREDICTION_COLUMNS, self.properties)))
        for m in PARAMETERS['input_mapping']:
            self.row[m['assessment_column']] = 'LOW reliability'
            self.row[m['adi_column']] = 0.1

    def fixture(self):
        records = []
        for i, state in enumerate(['exact_key_match', 'review_required', 'no_report_association', 'exact_key_match'], 1):
            record = {**self.row.to_dict(), 'inchikey': f'full-key-{i}', 'qsar_inchikey': f'qsar-key-{i}',
                      'vega_row_no': i if i != 3 else '', 'qsar_identity_status': state,
                      'qsar_identity_verified': state == 'exact_key_match',
                      'qsar_identity_reason': 'formula_and_radical_representation_difference' if i == 2 else ''}
            if i == 3:
                for c in LRTP_REQUIRED_PREDICTION_COLUMNS: record[c] = ''
            if i == 4: record[LRTP_REQUIRED_PREDICTION_COLUMNS[1]] = 0
            records.append(record)
        pd.DataFrame(records).to_csv(self.folder/'compound_qsar.csv',index=False,encoding='utf-8',lineterminator='\n')
        pd.DataFrame([{'inchikey':'full-key-2','qsar_inchikey':'qsar-key-2','record_id':'source-7',
                       'source_native_id':'007','reported_fields_json':'{"SMILES":"original"}'}]).to_csv(
            self.folder/'identity_anomaly_sources.csv',index=False,encoding='utf-8',lineterminator='\n')
        pd.DataFrame([{'qsar_inchikey':'qsar-key-2','vega_row_no':2,'model_id':'example',
                       'source_sha256':'frozen-source','source_line_number':12}]).to_csv(
            self.folder/'identity_anomaly_reports.csv',index=False,encoding='utf-8',lineterminator='\n')
        self.refingerprint()

    def refingerprint(self):
        m={'output_sha256':{p.name:_file_hash(p) for p in self.folder.glob('*.csv')},
           'frozen_batch':{'identity_review_rows':[2]},
           'inputs':[{'filename':m['report_filename'],'sha256':m['report_sha256']} for m in PARAMETERS['input_mapping']]}
        (self.folder/'qsar_manifest.json').write_text(json.dumps(m),encoding='utf-8')

    def test_historical_example_has_independently_frozen_expected_values(self):
        # Archived first compound AAAQKTZKLRYKHR-UHFFFAOYSA-N, run 20261006T233429Z.
        r = _calculate_row_lrtp(self.row)
        self.assertEqual(r['LRTP_POV_days'], 847.3096719978843)
        self.assertEqual(r['LRTP_CTD_km'], 103.03951111859995)
        self.assertEqual(r['LRTP_TE_percent'], 5.2570628514283044e-08)
        self.assertEqual(r['LRTP_HLwater_h'],1704.0)
        self.assertEqual(r['LRTP_HLsoil_h'],16992.0)
        self.assertEqual(r['LRTP_input_status'],'ok')
        self.assertEqual(json.loads(r['LRTP_evidence'])['source_quality']['logKow']['ADI'],0.1)

    def test_log_partition_conversion_retains_sign_and_units(self):
        self.assertEqual(derive_log_kaw_from_vp_and_solubility(-6.5999,6.31),-1.6784282214382236)
        self.assertAlmostEqual(derive_log_kaw_from_vp_and_solubility(0,0),math.log10(101325/(1000*8.314*298.15)))

    def test_missing_nonfinite_and_nonpositive_half_lives_do_not_calculate(self):
        for value, status in [('', 'missing'), ('NaN','missing'), ('inf','missing'), (None,'missing'), (0,'invalid'),(-1,'invalid')]:
            with self.subTest(value=value),patch('plastprior.lrtp.calculate_oecd_lrtp') as kernel:
                row=self.row.copy();row[LRTP_REQUIRED_PREDICTION_COLUMNS[1]]=value
                r=_calculate_row_lrtp(row)
                self.assertEqual(r['LRTP_input_status'],status)
                self.assertIsNone(r['LRTP_POV_days'])
                kernel.assert_not_called()

    def test_warning_range_preserves_calculation_and_zero_log_partition_is_valid(self):
        row=self.row.copy();row[LRTP_REQUIRED_PREDICTION_COLUMNS[0]]=11
        self.assertEqual(_calculate_row_lrtp(row)['LRTP_input_status'],'warning')
        row[LRTP_REQUIRED_PREDICTION_COLUMNS[0]]=0
        self.assertEqual(_calculate_row_lrtp(row)['LRTP_input_status'],'ok')
        row[LRTP_REQUIRED_PREDICTION_COLUMNS[0]]=101
        self.assertEqual(_calculate_row_lrtp(row)['LRTP_input_status'],'invalid')

    def test_reference_line_equality_does_not_exceed(self):
        result={'POV_days':194.662,'CTD_km':5096.73,'TE_percent':2.2476,'PhiAir':0.2,'emission_scenarios':{}}
        with patch('plastprior.lrtp.calculate_oecd_lrtp',return_value=result):
            r=_calculate_row_lrtp(self.row)
        for c in LRTP_OUTPUT_COLUMNS[9:12]:self.assertFalse(r[c])
        result.update(POV_days=194.663,CTD_km=5096.731,TE_percent=2.2477)
        with patch('plastprior.lrtp.calculate_oecd_lrtp',return_value=result):
            r=_calculate_row_lrtp(self.row)
        for c in LRTP_OUTPUT_COLUMNS[9:12]:self.assertTrue(r[c])

    def test_solver_pivots_and_detects_singular_matrix(self):
        self.assertEqual(_solve_linear_3x3([[0,1,0],[1,0,0],[0,0,2]],[2,1,6]),[1,2,3])
        with self.assertRaisesRegex(ValueError,'Singular'):
            _solve_linear_3x3([[1,1,1],[1,1,1],[1,1,1]],[1,1,1])

    def test_solver_failure_and_nonfinite_outputs_are_audited(self):
        with patch('plastprior.lrtp.calculate_oecd_lrtp',side_effect=ValueError('Singular mass-balance matrix')):
            r=_calculate_row_lrtp(self.row)
        self.assertEqual(r['LRTP_input_status'],'calculation_error')
        self.assertIn('Singular',r['LRTP_evidence'])
        with patch('plastprior.lrtp.calculate_oecd_lrtp',return_value={'POV_days':float('inf'),'CTD_km':1,'TE_percent':1,'PhiAir':0}):
            self.assertEqual(_calculate_row_lrtp(self.row)['LRTP_input_status'],'calculation_error')
        with self.assertRaisesRegex(ValueError,'finite'):
            calculate_oecd_lrtp(log_kaw=float('nan'),log_kow=1,hl_air_h=1,hl_water_h=1,hl_soil_h=1)

    def test_historical_values_survive_but_unverified_analysis_values_are_missing(self):
        self.fixture(); before={p.name:_file_hash(p) for p in self.folder.iterdir()}
        r=integrate_lrtp(self.folder)
        self.assertEqual(before,{p.name:_file_hash(p) for p in self.folder.iterdir()})
        h=r.historical.set_index('inchikey');a=r.compounds.set_index('inchikey')
        self.assertEqual(h.loc['full-key-1','LRTP_POV_days'],h.loc['full-key-2','LRTP_POV_days'])
        self.assertTrue(a.loc['full-key-1','lrtp_available'])
        for key in ('full-key-2','full-key-3','full-key-4'):
            self.assertFalse(a.loc[key,'lrtp_available'])
            self.assertTrue(a.loc[key,VALUE_COLUMNS].isna().all())
        self.assertEqual(a.loc['full-key-2','calculation_status'],'ok')
        self.assertEqual(a.loc['full-key-2','LRTP_input_status'],'identity_review_required')
        self.assertEqual(a.loc['full-key-2','lrtp_exclusion_reason'],'identity_review_required')
        self.assertNotIn('LRTP_evidence',a)
        self.assertEqual(len(r.isolation_audit),12)
        self.assertEqual(r.anomaly_sources.iloc[0]['source_native_id'],'007')
        self.assertEqual(r.anomaly_reports.iloc[0]['source_line_number'],'12')
        self.assertEqual(r.anomaly_sources.iloc[0]['identity_reason'],'formula_and_radical_representation_difference')
        out=self.folder/'output';r.write_reports(out)
        manifest=json.loads((out/'lrtp_manifest.json').read_text(encoding='utf-8'))
        for f,d in manifest['output_sha256'].items():self.assertEqual(_file_hash(out/f),d)
        reread=pd.read_csv(out/'compound_lrtp.csv',dtype=str,keep_default_na=False,encoding="utf-8").set_index('inchikey')
        self.assertEqual(reread.loc['full-key-2','LRTP_POV_exceeds_oecd_default'],'')
        self.assertFalse(any('score' in c.lower() for c in reread))

    def test_changed_upstream_bytes_and_inconsistent_identity_flags_fail(self):
        self.fixture();p=self.folder/'compound_qsar.csv'
        p.write_text(p.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'fingerprint'):integrate_lrtp(self.folder)
        frame=pd.read_csv(p,dtype=str,keep_default_na=False,encoding="utf-8");frame.loc[1,'qsar_identity_verified']='True'
        frame.to_csv(p,index=False,encoding='utf-8');self.refingerprint()
        with self.assertRaisesRegex(ValueError,'flag disagree'):integrate_lrtp(self.folder)

    def test_missing_property_column_fails_instead_of_silently_creating_missing_results(self):
        self.fixture();p=self.folder/'compound_qsar.csv'
        frame=pd.read_csv(p,dtype=str,keep_default_na=False,encoding="utf-8").drop(columns=LRTP_REQUIRED_PREDICTION_COLUMNS[0])
        frame.to_csv(p,index=False,encoding='utf-8');self.refingerprint()
        with self.assertRaisesRegex(ValueError,'Missing LRTP source columns'):integrate_lrtp(self.folder)

    def test_regression_compares_nested_scenarios_and_distinguishes_missing_zero_false(self):
        a='{"result":{"air":0.10},"flags":[],"status":"ok"}'
        b='{"flags":[],"status":"ok","result":{"air":0.1}}'
        self.assertEqual(_compare_evidence(a,b,'key'),[])
        self.assertEqual(len(_compare_evidence(a,b.replace('0.1','0.10000000000001'),'key')),1)
        self.assertTrue(_compare_evidence('{"v":false}','{"v":0}','key'))
        old=pd.DataFrame([{'key':'a','number':'0','flag':'False'}]);new=pd.DataFrame([{'key':'a','number':'','flag':''}])
        self.assertEqual(len(_compare_qsar_frame(old,new,'key',{'number':'number','flag':'flag'},{'number'},'test')),2)


if __name__ == '__main__':
    unittest.main()
