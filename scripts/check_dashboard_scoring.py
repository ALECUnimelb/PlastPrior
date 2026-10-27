"""Compare the complete rounded CSV with the Dashboard's independent integer arithmetic."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plastprior.scoring_scenarios import COMPONENT_MAXIMA, default_policy

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--csv',type=Path,required=True)
parser.add_argument('--dashboard-root',type=Path,required=True)
parser.add_argument('--report',type=Path)
args=parser.parse_args()
with args.csv.open(newline='') as f: rows=list(csv.DictReader(f))
module=args.dashboard_root/'app/src/core/scoringScenario.js'
config_path=args.dashboard_root/'app/src/core/scenarioPolicy.json'
assert json.loads(config_path.read_text()) == default_policy(), 'Default configurations differ'
inputs=[{key:r[key] for key in ['inchikey',*COMPONENT_MAXIMA]} for r in rows]
code="""import fs from 'node:fs';
const {scoreScenario}=await import(process.argv[1]);
const {records,config}=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(scoreScenario(records,config)));
"""
# Configuration is embedded in every formal row; this also supports custom exports.
configs={r['scoring_config_json'] for r in rows}
assert len(configs)==1, 'Mixed configurations in CSV'
result=subprocess.run(['node','--input-type=module','-e',code,module.resolve().as_uri()],
    input=json.dumps({'records':inputs,'config':json.loads(next(iter(configs)))}),capture_output=True,text=True,check=True)
calculated=json.loads(result.stdout)
numeric=['Hazard_score','Exposure_score','Hazard_score_raw','Exposure_score_raw',
         'Priority_score','Priority_level','Priority_rank','Priority_tie_size']
for before,after in zip(rows,calculated,strict=True):
    assert before['inchikey']==after['inchikey']
    for field in numeric:
        a=None if before[field]=='' else Decimal(before[field])
        b=None if after[field] is None else Decimal(str(after[field]))
        assert a==b,(before['inchikey'],field,a,b)
    for field in ['Hazard_label','Exposure_label','Priority_tier','Priority_data_status']:
        assert before[field]==after[field],(before['inchikey'],field)
    expected=None if before['Top_n_selected']=='' else before['Top_n_selected']=='True'
    assert after['Top_n_selected']==expected
report={'status':'passed','rows':len(rows),'numeric_fields':numeric,
        'checks':['labels','priority level','evidence status','competition ties','inclusive Top-N','default policy parity'],
        'csv_sha256':hashlib.sha256(args.csv.read_bytes()).hexdigest(),
        'dashboard_implementation_sha256':hashlib.sha256(module.read_bytes()).hexdigest()}
if args.report: args.report.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
