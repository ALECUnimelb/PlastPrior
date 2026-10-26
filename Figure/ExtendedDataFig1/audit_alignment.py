"""Check rendered UpSet column/row alignment against the current source tables."""
from pathlib import Path
import csv,json,re,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent

def check():
    output=HERE/'output'
    rows=lambda p:list(csv.DictReader(p.open()))
    repo=HERE.parents[1]
    lock=json.loads((repo/'Figure/figure_sources.json').read_text())
    data=repo/lock['figure_data_dir']/HERE.name
    columns=rows(data/'overlap/selected.csv')
    sizes=rows(data/'overlap/set_sizes.csv')
    colors={r['color'].upper() for r in sizes}
    root=ET.parse(output/'ExtendedDataFig1.svg').getroot()
    ns={'s':'http://www.w3.org/2000/svg'}
    assert not root.findall('.//s:g[@transform]',ns)
    rects=root.findall('.//s:rect',ns)
    def fill(e):
        m=re.search(r'(?:^|;)\s*fill:\s*(#[0-9A-Fa-f]{6})',e.get('style',''))
        return m[1].upper() if m else None
    bars=[r for r in rects if fill(r)=='#26394C']
    dots=root.findall('.//s:circle',ns)
    xs=sorted({float(d.get('cx')) for d in dots});ys=sorted({float(d.get('cy')) for d in dots})
    centres=sorted(float(r.get('x'))+float(r.get('width'))/2 for r in bars)
    assert len(centres)==len(xs)==len(columns)
    assert len(ys)==len(sizes) and len(dots)==len(columns)*len(sizes)
    row_bars=[r for r in rects if fill(r) in colors and float(r.get('x',0))<min(xs) and float(r.get('y',0))>min(ys)-10]
    row_centres=sorted(float(r.get('y'))+float(r.get('height'))/2 for r in row_bars)
    assert len(row_centres)==len(sizes)
    dx=max(abs(a-b) for a,b in zip(centres,xs));dy=max(abs(a-b) for a,b in zip(row_centres,ys))
    assert dx<=.02 and dy<=.02
    return {'passed':True,'columns':len(xs),'rows':len(ys),'max_column_error_pt':dx,'max_row_error_pt':dy}
if __name__=='__main__':print(json.dumps(check(),indent=2))
