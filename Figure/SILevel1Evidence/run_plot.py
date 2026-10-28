"""Build one SI review, verify it, or promote a user-approved snapshot."""
from pathlib import Path
from tempfile import mkdtemp
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

MODULE=Path(__file__).resolve().parent
ROOT=MODULE.parents[1]
NAME=MODULE.name
STEM='Supplementary_Table_Level1'
RUNTIME=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
NODE=Path(os.environ.get('PLASTPRIOR_ARTIFACT_NODE',RUNTIME/'node/bin/node'))
NODE_MODULES=Path(os.environ.get('PLASTPRIOR_ARTIFACT_MODULES',RUNTIME/'node/node_modules'))
spec=importlib.util.spec_from_file_location('si_level1_prepare',MODULE/'prepare.py')
preparation=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparation)
sha=preparation.sha
sys.path.insert(0,str(ROOT/'Figure/_shared'))
from managed import replace_pair
from result_paths import figure_paths, relocated, resolve, verify_code, RESULT, manifest_path


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def paths(state):
    return figure_paths(NAME, state)


def code_hashes():
    files=[MODULE/n for n in ['prepare.py','build.R','export_excel.mjs','run_plot.py','source.json']]
    files.extend([ROOT/'Figure/_shared/managed.py', ROOT/'Figure/_shared/result_paths.py'])
    return {str(p.relative_to(ROOT)):sha(p) for p in files}


def verify_xlsx(path,payload,qa):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]
        book=ET.fromstring(z.read('xl/workbook.xml'))
        assert [s.attrib['name'] for s in book.findall('s:sheets/s:sheet',ns)]==['Level1 evidence','Definitions']
        sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        cells={c.attrib['r']:c for c in sheet.findall('.//s:sheetData/s:row/s:c',ns)}
        def name(i):
            result=''
            while i:
                i,r=divmod(i-1,26);result=chr(65+r)+result
            return result
        def value(c):
            if c is None:return None
            assert c.find('s:f',ns) is None,'Source snapshot unexpectedly contains a formula'
            if c.attrib.get('t')=='inlineStr':return ''.join(c.find('s:is',ns).itertext())
            v=c.find('s:v',ns)
            if v is None or v.text is None:return None
            if c.attrib.get('t')=='s':return strings[int(v.text)]
            if c.attrib.get('t')=='str':return v.text
            if c.attrib.get('t')=='e':raise AssertionError('Excel cell error: '+v.text)
            return float(v.text)
        for rownum,row in enumerate(payload['rows'],6):
            for colnum,column in enumerate(qa['columns'],1):
                expected=row.get(column['field'])
                actual=value(cells.get(f'{name(colnum)}{rownum}'))
                if expected=='':expected=None
                if isinstance(expected,str) and expected.startswith('='):expected="'"+expected
                assert actual==expected,(rownum,column['field'],actual,expected)
                if column['type']=='text' and expected is not None:
                    assert isinstance(actual,str),(rownum,column['field'],'not text')
        actual_data_rows=[r for r in sheet.findall('s:sheetData/s:row',ns) if int(r.attrib['r'])>=6 and any(value(c) is not None for c in r.findall('s:c',ns))]
        assert len(actual_data_rows)==len(payload['rows'])
        pane=sheet.find('s:sheetViews/s:sheetView/s:pane',ns)
        assert pane is not None and float(pane.attrib.get('xSplit','0'))==3 and float(pane.attrib.get('ySplit','0'))==5,('Freeze panes',None if pane is None else pane.attrib)
        tables=[ET.fromstring(z.read(n)) for n in z.namelist() if n.startswith('xl/tables/') and n.endswith('.xml')]
        assert len(tables)==1 and tables[0].find('s:autoFilter',ns) is not None
        assert tables[0].attrib['ref']==f'A5:{name(len(qa["columns"]))}{len(payload["rows"])+5}'
        rules=sheet.findall('s:conditionalFormatting/s:cfRule',ns)
        assert len(rules)>=len(payload['score_palette'])+len(payload['regulatory_legend'])
        assert not any(c.attrib.get('t')=='e' for name_ in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'] for c in ET.fromstring(z.read(name_)).findall('.//s:c',ns))
    return {'passed':True,'rows':len(payload['rows']),'native_values_match':True,'identifiers_are_text':True,'freeze_rows':5,'freeze_columns':3,'filter_table':True,'conditional_format_rules':len(rules)}


def verify_pdf(path,payload,qa):
    from pypdf import PdfReader
    pdf=PdfReader(path)
    assert len(pdf.pages)==qa['pages'],('PDF page count',len(pdf.pages),qa['pages'])
    assert sum(qa['rows_per_page'])==len(payload['rows'])
    offset=0
    for page,count in zip(pdf.pages,qa['rows_per_page']):
        text=page.extract_text()
        assert len(text)>50,'Blank PDF page'
        compact=re.sub(r'\s+','',text)
        for row in payload['rows'][offset:offset+count]:
            assert re.sub(r'\s+','',row['Name']) in compact,('PDF missing compound',row['Name'])
        offset+=count
    return {'passed':True,'pages':len(pdf.pages),'all_compound_names_present':True}


def verify(state='review',working=True):
    folder,data=paths(state)
    manifest=relocated(json.loads(manifest_path(NAME).read_text()))
    assert manifest['status']==('review' if state=='review' else 'approved')
    assert manifest['source_data_dir']==str(data.relative_to(ROOT))
    assert {str(p.relative_to(data)) for p in data.rglob('*') if p.is_file()}==set(manifest['source_data'])
    for name,digest in manifest['outputs'].items():assert sha(folder/name)==digest,('Output changed',name)
    for name,digest in manifest['source_data'].items():assert sha(data/name)==digest,('Data changed',name)
    if working:
        verify_code(manifest['code'], code_hashes())
        for path,digest in manifest['sources'].items():assert sha(resolve(path))==digest,('Input changed',path)
    payload=json.loads((data/'si_payload.json').read_text())
    qa=verify_xlsx(folder/f'{STEM}.xlsx',payload,manifest['qa']['workbook'])
    pdf=verify_pdf(folder/f'{NAME}.pdf',payload,manifest['qa']['figure'])
    return {'passed':True,'status':manifest['status'],'run_id':manifest['run_id'],'compounds':len(payload['rows']),'pdf':pdf,'xlsx':qa}


def refresh_index():
    catalog=json.loads((ROOT/'Figure/catalog.json').read_text())
    lines=['# SI 文件清单','','每项只保留一套当前文件；确认与待审是状态，不是并行目录。','',
           '| 项目 | 当前状态 | 文件 | 说明 |','|---|---|---|---|']
    for name,item in catalog.get('supplementary',{}).items():
        status='待审' if item['review'] else '已确认'
        links=f'[Excel](../result/figures/{STEM}.xlsx) · [PDF](../result/figures/{name}.pdf)'
        lines.append(f'| Level 1 evidence | {status} | {links} | {item["note"]} |')
    lines+=['','[主图与扩展图清单](INDEX.md)','']
    (ROOT/'Figure/SI_INDEX.md').write_text('\n'.join(lines))


def register(**changes):
    path=ROOT/'Figure/catalog.json';catalog=json.loads(path.read_text())
    item=catalog.setdefault('supplementary',{}).setdefault(NAME,{'formal':'none','review':False,'entrypoint':f'Figure/{NAME}/run_plot.py'})
    item.update(changes);write_json(path,catalog);refresh_index()


def build(args):
    payload=preparation.make_payload(args.run_dir,args.annotations,args.policy)
    current=paths('output')[1]/'si_payload.json'
    if not current.exists():current=paths('review')[1]/'si_payload.json'
    if current.exists():
        before={r['inchikey'] for r in json.loads(current.read_text())['rows']}
        after={r['inchikey'] for r in payload['rows']}
        payload['changes']['membership_change']={'added':sorted(after-before),'removed':sorted(before-after)}
    else:payload['changes']['membership_change']={'comparison':'First managed SI review'}
    stage=Path(mkdtemp(prefix='.building-',dir=MODULE));data_stage=None
    try:
        preparation.write_payload(payload,stage/'source_data')
        subprocess.run(['Rscript',str(MODULE/'build.R'),str(stage/'source_data/si_payload.json'),str(stage)],cwd=ROOT,check=True)
        (stage/'node_modules').symlink_to(NODE_MODULES,target_is_directory=True)
        (stage/'export_excel.mjs').symlink_to(MODULE/'export_excel.mjs')
        subprocess.run([str(NODE),'--preserve-symlinks-main',str(stage/'export_excel.mjs'),str(stage/'source_data/si_payload.json'),str(stage)],cwd=ROOT,check=True)
        (stage/'node_modules').unlink();(stage/'export_excel.mjs').unlink()
        figure_qa=json.loads((stage/'figure_qa.json').read_text())
        figure_qa['export_validation']=verify_pdf(stage/f'{NAME}.pdf',payload,figure_qa)
        workbook_qa=json.loads((stage/'workbook_qa.json').read_text())
        workbook_qa['export_validation']=verify_xlsx(stage/f'{STEM}.xlsx',payload,workbook_qa)
        # Native Excel opening view is the single retained preview. R's page-one
        # image and other worksheet renders are temporary visual QA material.
        (stage/f'{NAME}.png').rename(stage/'.qa/figure.png')
        shutil.copyfile(stage/'.qa/excel_top.png',stage/f'{NAME}.png')
        if args.keep_qa:
            qa_dir=ROOT/'audit_archive/si_level1/qa'
            if qa_dir.exists():shutil.rmtree(qa_dir)
            shutil.copytree(stage/'.qa',qa_dir)
        shutil.rmtree(stage/'.qa');(stage/'figure_qa.json').unlink();(stage/'workbook_qa.json').unlink()
        (stage/f'{STEM}.xlsx.inspect.ndjson').unlink(missing_ok=True)
        for path,digest in payload['metadata']['sources'].items():
            assert sha(resolve(path))==digest,('Input modified during generation',path)
        images,data_target=paths('review')
        manifest={'schema_version':1,'kind':'supplementary_table','status':'review','figure':NAME,
                  'run_id':payload['metadata']['run_id'],'sources':payload['metadata']['sources'],'code':code_hashes(),
                  'source_data_dir':str(data_target.relative_to(ROOT)),
                  'source_data':{p.name:sha(p) for p in sorted((stage/'source_data').iterdir())},
                  'outputs':{p.name:sha(p) for p in sorted(stage.iterdir()) if p.is_file()},
                  'qa':{'figure':figure_qa,'workbook':workbook_qa},'changes':payload['changes'],
                  'facts':{'cohort_size':len(payload['rows']),'classification':'five-level figure policy; all source scores/ranks retained',
                           'preview':'Native Excel view of the first rows; the workbook and PDF contain the complete cohort'}}
        write_json(stage/'manifest.json',manifest)
        data_target.parent.mkdir(parents=True,exist_ok=True)
        data_stage=Path(mkdtemp(prefix='.building-',dir=data_target.parent));data_stage.rmdir()
        (stage/'source_data').rename(data_stage)
        replace_pair(stage,data_stage,images,data_target)
        register(review=True,note=f'{len(payload["rows"])} 个化合物，Excel 与完整 PDF 待审')
        print(json.dumps(verify(),ensure_ascii=False))
        print(f'Review workbook: {images/STEM}.xlsx')
    finally:
        for p in [stage,data_stage]:
            if p and p.exists():shutil.rmtree(p)


def approve():
    verify('review',working=True)
    manifest=relocated(json.loads(manifest_path(NAME).read_text()))
    manifest['status']='approved'
    write_json(manifest_path(NAME),manifest)
    register(formal='current',review=False,note=f'{manifest["facts"]["cohort_size"]} 个化合物，已认可')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--verify',action='store_true');action.add_argument('--approve',action='store_true')
    parser.add_argument('--run-dir',type=Path);parser.add_argument('--annotations',type=Path);parser.add_argument('--policy',type=Path)
    parser.add_argument('--keep-qa',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.approve:approve()
    elif args.verify:
        state='review' if json.loads(manifest_path(NAME).read_text())['status']=='review' else 'output'
        print(json.dumps(verify(state,working=state=='review'),ensure_ascii=False,indent=2))
    else:build(args)
