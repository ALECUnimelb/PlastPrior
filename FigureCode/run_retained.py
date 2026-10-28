"""Refresh an explicitly retained figure at its single fixed destination."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'FigureCode/_shared'))
from managed import replace_pair
from result_paths import figure_paths

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('figure',choices=['Level1Identity','Level1IdentityTree'])
    name=parser.parse_args().figure
    images,data=figure_paths(name)
    with tempfile.TemporaryDirectory(prefix='.retained-',dir=ROOT) as temp:
        stage=Path(temp)/'images';stage.mkdir()
        tables=Path(temp)/'data'
        subprocess.run(['Rscript',str(ROOT/'FigureCode/Supplementary'/name/'build.R'),str(stage)],cwd=ROOT,check=True)
        if (stage/'source_data').exists():
            (stage/'source_data').rename(tables)
        else:shutil.copytree(data,tables)
        for p in stage.iterdir():
            if p.suffix=='.svg' or '.preview.' in p.name:p.unlink()
        record=json.loads((stage/'manifest.json').read_text())
        record['output_hashes']={n:h for n,h in record['output_hashes'].items() if (stage/n).exists()}
        (stage/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
        replace_pair(stage,tables,images,data)
if __name__=='__main__':main()
