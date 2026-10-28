// Native SI workbook; published scores are snapshots from the pinned data run.
import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

const [payloadPath, outputDir] = process.argv.slice(2);
if (!payloadPath || !outputDir) throw new Error('Usage: export_excel.mjs payload.json output-directory');
const payload=JSON.parse(await fs.readFile(payloadPath,'utf8'));
const {rows,components,metadata,score_palette,regulatory_legend}=payload;
const ink='#263440', muted='#69747D', teal='#326F78', warm='#9D5149';
const colName=i=>{let s='';for(i++;i>0;i=Math.floor((i-1)/26))s=String.fromCharCode(65+(i-1)%26)+s;return s;};
const literal=v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v;
const columns=[
 ['ID','Display_ID',50,'text'],['Compound','Name',340,'text'],['CAS','CAS',110,'text'],
 ['Primary use','primary_use_display',225,'text'],['H','Hazard_score',48,'number'],
 ['E','Exposure_score',48,'number'],['Total','Priority_score',58,'number'],['Rank','Priority_rank',58,'number'],
 ...components.map(c=>[`${c.abbreviation}\n×${c.weight}`,c.field,46,'number']),
 ['Code','Regulatory_code',60,'text'],['InChIKey','inchikey',280,'text'],
 ['H raw','Hazard_score_raw',80,'number'],['E raw','Exposure_score_raw',80,'number'],
 ['H label','Figure_hazard_label',70,'text'],['E label','Figure_exposure_label',70,'text'],
 ['Figure level','Figure_priority_level',85,'number'],['Source level','Source_priority_level',85,'number'],
 ['Primary use (full)','primary_use',245,'text'],['Detailed uses','detailed_uses',460,'text'],
 ['GIC annotation','Regulatory_name',260,'text'],['Annotation status','annotation_status',230,'text'],
 ['Annotation source','annotation_source',320,'text'],['Annotation review','annotation_review_status',225,'text'],
 ['Missing components','missing_components',165,'text'],['Annotation ID','annotation_id',115,'text'],
];
const wb=Workbook.create();
const sheet=wb.worksheets.add('Level1 evidence');
const defs=wb.worksheets.add('Definitions');
sheet.showGridLines=false;defs.showGridLines=false;
sheet.tabColor=teal;defs.tabColor='#AEB7C2';
const last=rows.length+5,lastCol=colName(columns.length-1);
sheet.getRange(`A1:${lastCol}${last}`).format={font:{name:'Arial',size:10,color:ink},fill:'#FFFFFF',verticalAlignment:'center'};
columns.forEach(([header,field,width,type],i)=>{
 const letter=colName(i);sheet.getRange(`${letter}1:${letter}${last}`).format.columnWidthPx=width;
 sheet.getRange(`${letter}6:${letter}${last}`).setNumberFormat(type==='text'?'@':'0.##');
});
sheet.mergeCells('A2:S2');sheet.getRange('A2').values=[['Level 1 compound evidence']];
sheet.getRange('A2:S2').format.font={name:'Arial',size:14,bold:true,color:ink};
sheet.getRange('A2:S2').format.rowHeight=24;
sheet.mergeCells('A3:S3');
sheet.getRange('A3').values=[[`${metadata.cohort_size} compounds. Original scores and ranks retained. Grey blank component cells indicate missing evidence; zero is a recorded score.`]];
sheet.getRange('A3:S3').format.font={name:'Arial',size:10,color:muted};
sheet.getRange('A3:S3').format.rowHeight=27;
for(const [range,title,color] of [['A4:D4','IDENTITY AND PRIMARY USE',muted],['E4:H4','EXISTING SCORES',muted],['I4:L4','HAZARD',warm],['M4:R4','EXPOSURE',teal],['S4:S4','GIC',muted],[`T4:${lastCol}4`,'IDENTIFIERS, RAW TOTALS AND ANNOTATIONS',muted]]){
 if(!range.startsWith('S4:'))sheet.mergeCells(range);
 const r=sheet.getRange(range);r.values=[[title]];r.format.font={name:'Arial',size:10,bold:true,color};r.format.rowHeight=24;
}
sheet.getRange(`A5:${lastCol}5`).values=[columns.map(c=>c[0])];
const expected=rows.map(r=>columns.map(([,field])=>literal(r[field]??null)));
sheet.getRange(`A6:${lastCol}${last}`).values=expected;
const table=sheet.tables.add(`A5:${lastCol}${last}`,true,'Level1Evidence');
table.style='TableStyleLight1';
table.showFilterButton=true;table.showTotals=false;table.showBandedColumns=false;
sheet.getRange(`A5:${lastCol}5`).format={fill:'#FFFFFF',font:{name:'Arial',size:10,bold:true,color:ink},wrapText:true,
 horizontalAlignment:'center',verticalAlignment:'center',rowHeight:36,borders:{bottom:{style:'thin',color:'#69747D'}}};
sheet.getRange(`A6:${lastCol}${last}`).format.wrapText=true;
for(let i=0;i<rows.length;i++){
 const r=i+6;
 const row=sheet.getRange(`A${r}:${lastCol}${r}`);
 row.format.fill=i%2?'#F7F9FA':'#FFFFFF';
 const lines=Math.max(...columns.map(([,field,width])=>Math.ceil(String(rows[i][field]??'').length/Math.max(4,(width-12)/6.3))));
 row.format.rowHeight=Math.max(29,lines*13+9);
 for(let c=4;c<columns.length;c++)if(columns[c][3]==='number'){
  const v=rows[i][columns[c][1]];
  sheet.getRange(`${colName(c)}${r}`).setNumberFormat(v==null||Number.isInteger(v)?'0':(Number.isInteger(v*10)?'0.0':'0.00'));
 }
}
sheet.getRange(`A6:D${last}`).format.horizontalAlignment='left';
sheet.getRange(`E6:S${last}`).format.horizontalAlignment='center';
sheet.getRange(`T6:${lastCol}${last}`).format.horizontalAlignment='left';
for(const letter of ['U','V','Y','Z'])sheet.getRange(`${letter}6:${letter}${last}`).format.horizontalAlignment='right';
sheet.getRange(`A6:A${last}`).format.font.color=muted;
sheet.getRange(`C6:C${last}`).format.font.color=muted;
sheet.getRange(`H6:H${last}`).format.font.color=muted;
sheet.getRange(`E6:E${last}`).format={fill:'#F2E4E1',font:{bold:true,color:warm}};
sheet.getRange(`F6:F${last}`).format={fill:'#E5EFF0',font:{bold:true,color:teal}};
sheet.getRange(`G6:G${last}`).format.font.bold=true;
const componentRange=sheet.getRange(`I6:R${last}`);
componentRange.format.fill='#E3E6E9';
componentRange.format.borders={preset:'all',style:'thin',color:'#FFFFFF'};
for(const [score,fill] of Object.entries(score_palette)){
 componentRange.conditionalFormats.addCustom(`AND(ISNUMBER(I6),I6=${score})`,{fill,font:{color:Number(score)===2?'#FFFFFF':ink}});
}
for(const item of regulatory_legend){
 sheet.getRange(`S6:S${last}`).conditionalFormats.addCustom(`S6="${item.code}"`,{fill:item.colour,font:{bold:true,color:['A','B'].includes(item.code)?'#FFFFFF':ink}});
}
sheet.freezePanes.freezeRows(5);sheet.freezePanes.freezeColumns(3);

// A separate dictionary keeps all definitions and provenance in one place.
const definitions=[
 ['Population',`${metadata.cohort_size} Level 1 compounds out of ${metadata.population_size} compounds in the selected run.`],
 ['Cohort rule',`Five-level figure policy: both rounded H and E have the vH label (currently ≥${metadata.cutpoints[2]}). Membership is not a Top-N selection.`],
 ['ID','Display row number, formatted as text. It is not a rank or a permanent chemical identifier; use InChIKey for joins.'],
 ['Rank','Existing all-compound competition rank. Ties retain the same rank and may leave gaps. Rows sort by total score descending, then InChIKey.'],
 ['H / E / Total','Existing rounded hazard, exposure and priority scores. Total is the source value H + E. No scores or ranks are recalculated in this workbook.'],
 ['H raw / E raw','Unrounded weighted domain totals retained from the source for audit. Each domain was rounded once, with 0.5 rounding up.'],
 ['Component cells','Unweighted source component scores. Weight multipliers appear in their column headers. Grey blank cells mean missing evidence; numeric zero remains a valid recorded score.'],
 ['Missing components','Lists the abbreviations of unavailable component scores for that compound, independently of colour.'],
 ['Primary / detailed uses','User-supplied annotations joined by full InChIKey. A primary use is one display category; detailed uses may overlap. Unclassified compounds remain in the table.'],
 ['Annotation status','Indicates an available annotation, missing classification, or changed identity labels requiring review.'],
 ['Annotation source / review','Per-compound source and review notes when supplied. A blank source means no row-level citation was provided; it does not indicate independent verification.'],
 ['Figure / source level','Figure level uses the five-level policy; source level preserves the CSV classification, which currently has four levels. These are distinct classifications.'],
 ['CAS / InChIKey','Chemical identifiers stored as text. Name and CAS are current source values; InChIKey is the join key.'],
 ['GIC','Regulatory annotation as recorded in the selected database version. Full descriptions are retained beside the codes. These annotations do not contribute scoring points.'],
 ['Workbook use','A published data snapshot for sorting, filtering and inspection. Regenerate from the selected run to update data; editing cells does not apply a scoring scenario.'],
 ...components.map(c=>[`${c.abbreviation} ×${c.weight}`,`${c.name}; unweighted score, weight ${c.weight}; maximum ${['FC','HB'].includes(c.abbreviation)?1:2}.`]),
 ...Object.keys(score_palette).sort((a,b)=>Number(a)-Number(b)).map(s=>[`Score ${s}`,`A recorded unweighted component score of ${s}.`]),
 ...regulatory_legend.map(c=>[`GIC ${c.code}`,c.label]),
 ['Data run',metadata.run_id],['Figure policy',metadata.policy_version],
 ['Domain label cutpoints',`L <${metadata.cutpoints[0]}; M ≥${metadata.cutpoints[0]} and <${metadata.cutpoints[1]}; H ≥${metadata.cutpoints[1]} and <${metadata.cutpoints[2]}; vH ≥${metadata.cutpoints[2]}.`],
 ['Publication CSV SHA-256',metadata.source_csv_sha256],['Use annotations SHA-256',metadata.annotation_sha256],
 ['Source files','PlastPrior_results.csv, scoring_config.json and the paired scenario manifest; supplied use annotations and the five-level figure policy.'],
 ['Refresh findings',`${payload.changes.unclassified.length} compounds await classification; ${payload.changes.issues.filter(x=>x.issue.startsWith('Identity')).length} identity-label changes require review.`],
];
const defEnd=definitions.length+4;
defs.getRange(`A1:B${defEnd}`).format={fill:'#FFFFFF',font:{name:'Arial',size:10,color:ink},verticalAlignment:'center'};
defs.getRange(`A1:A${defEnd}`).format.columnWidthPx=225;
defs.getRange(`B1:B${defEnd}`).format.columnWidthPx=790;
defs.mergeCells('A2:B2');defs.getRange('A2').values=[['Definitions and data provenance']];
defs.getRange('A2:B2').format.font={name:'Arial',size:14,bold:true,color:ink};defs.getRange('A2:B2').format.rowHeight=26;
defs.getRange('A4:B4').values=[['Field / code','Definition']];defs.getRange('A4:B4').format={font:{bold:true},rowHeight:25,borders:{bottom:{style:'thin',color:muted}}};
defs.getRange(`A5:B${defEnd}`).values=definitions;
defs.getRange(`A5:B${defEnd}`).format.wrapText=true;
for(let i=0;i<definitions.length;i++){
 const range=defs.getRange(`A${i+5}:B${i+5}`);range.format.fill=i%2?'#F7F9FA':'#FFFFFF';
 range.format.rowHeight=Math.max(29,Math.ceil(definitions[i][1].length/115)*14+10);
 const score=definitions[i][0].startsWith('Score ')?definitions[i][0].slice(6):null;
 if(score!==null){defs.getRange(`A${i+5}`).format.fill=score_palette[score];defs.getRange(`A${i+5}`).format.font.color=score==='2'?'#FFFFFF':ink;}
 const gic=regulatory_legend.find(c=>definitions[i][0]===`GIC ${c.code}`);
 if(gic){defs.getRange(`A${i+5}`).format.fill=gic.colour;defs.getRange(`A${i+5}`).format.font.color=['A','B'].includes(gic.code)?'#FFFFFF':ink;}
}
wb.recalculate();
const observed=sheet.getRange(`A6:${lastCol}${last}`).values;
if(JSON.stringify(observed)!==JSON.stringify(expected))throw new Error('Native cell values differ from the prepared source');
const errorScan=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:50},maxChars:1500});
const inspect=await wb.inspect({kind:'table',range:'Level1 evidence!A5:S9',include:'values,formulas',tableMaxRows:5,tableMaxCols:19,maxChars:3000});
await fs.mkdir(outputDir,{recursive:true});
const qaDir=path.join(outputDir,'.qa');await fs.mkdir(qaDir,{recursive:true});
for(const [name,sheetName,range] of [
 ['excel_top','Level1 evidence','A1:S16'],
 ['excel_middle','Level1 evidence',`A${Math.max(6,Math.floor(last/2)-5)}:S${Math.min(last,Math.floor(last/2)+5)}`],
 ['excel_bottom','Level1 evidence',`A${Math.max(6,last-10)}:S${last}`],
 ['excel_details','Level1 evidence','T4:AH12'],
 ['excel_definitions','Definitions',`A1:B${defEnd}`],
]){
 const blob=await wb.render({sheetName,range,scale:1,format:'png'});
 await fs.writeFile(path.join(qaDir,`${name}.png`),new Uint8Array(await blob.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(outputDir,'Supplementary_Table_Level1.xlsx'));
await fs.writeFile(path.join(outputDir,'workbook_qa.json'),JSON.stringify({rows:rows.length,columns:columns.map(c=>({header:c[0],field:c[1],type:c[3]})),first_data_row:6,last_data_row:last,definitions_rows:defEnd,cell_values_identical:true,error_scan:errorScan.ndjson,inspection:inspect.ndjson},null,2));
console.log(`Native workbook exported: ${rows.length} compounds, ${columns.length} columns, two sheets.`);
