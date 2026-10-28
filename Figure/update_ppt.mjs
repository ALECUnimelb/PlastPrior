// Update the existing review deck from verified current figures; no plotting here.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

async function buildReviewDeck() {
 const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
 const runtime=path.join(process.env.HOME,'.cache/codex-runtimes/codex-primary-runtime/dependencies');
 const require=createRequire(path.join(runtime,'node/node_modules/@oai/artifact-tool/package.json'));
 const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
 const skill=process.env.PRESENTATIONS_SKILL_DIR ?? path.join(process.env.HOME,'.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11618/skills/presentations');
 const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
 process.env.RUNTIME_NODE_MODULES ??= path.join(runtime,'node/node_modules');
 const destinationDir=path.join(root,'result');
 execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'Figure/verify_figures.py')],{cwd:root,stdio:'pipe'});
 await fs.mkdir(destinationDir,{recursive:true});
 const build=await fs.mkdtemp(path.join(destinationDir,'.building-review-'));
 try {
 const existing=(await fs.readdir(destinationDir)).filter(n=>n.toLowerCase().endsWith('.pptx')&&!n.startsWith('~$'));
 if(existing.length>1)throw new Error('Keep one current PPTX in result before regenerating');
 const destination=path.join(destinationDir,existing[0]??'Figures.pptx');
 const catalog=JSON.parse(await fs.readFile(path.join(root,'Figure/catalog.json'),'utf8'));
 const hash=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
 const catalogHash=hash(await fs.readFile(path.join(root,'Figure/catalog.json')));
 const entries=[];const hashes=new Set();const sourceHashes=new Map();
 async function add(source,title,status) {
  const bytes=await fs.readFile(source);const sha=hash(bytes);
  const key=sha;
  sourceHashes.set(source,sha);
  if(hashes.has(key))return;
  hashes.add(key);entries.push({source,title,status,sha256:sha});
 }
 const figures=path.join(root,'result/figures');
 const mainNames=['Fig1','Fig2','Fig3','Fig4','Fig5','ExtendedDataFig1','ExtendedDataFig2','ExtendedDataFig3','ExtendedDataFig4'];
 for(const name of mainNames) {
  const item=catalog.figures[name];
  const folder=figures;
  const label=name.startsWith('Extended')?`Extended Data Fig. ${name.slice(-1)}`:`Fig. ${name.slice(-1)}`;
  const status=item.review?'Review':item.formal==='current'?'Approved':'Legacy — pending update';
  await add(path.join(folder,name+'.png'),label,status);
 }
 // The review deck contains exactly these nine manuscript figures.
 // Standalone Fig3b, SI tables, retained identity/tree and sensitivity assets
 // remain separate files and must never be appended automatically.
 if(entries.length!==9)throw new Error('Expected nine manuscript figure slides');
 console.log(`Review deck: ${entries.length} manuscript figure slides.`);
 const captions={};
 for(const section of (await fs.readFile(path.join(root,'Figure/captions_draft.md'),'utf8')).split('\n## ').slice(1)) {
  const [heading,...body]=section.split('\n');captions[heading.split(' | ')[0]]=body.join('\n').trim().replaceAll('**','');
 }
 // Fixed white 16:9 layout; no dependency on another historical PPTX.
 const p=Presentation.create({slideSize:{width:1280,height:720}});
 const addText=(slide,text,frame,size,color,bold=false,align='left')=>{
  const shape=slide.shapes.add({geometry:'textbox',position:frame,fill:'none',line:{fill:'none',width:0}});
  shape.text=text;shape.text.style={typeface:'Arial',fontSize:size,bold,color,alignment:align};return shape;
 };
 for(const [index,entry] of entries.entries()) {
  const input=entry.source;
  const asset=path.join(build,`asset-${index+1}.png`);
  // Resize only a private presentation copy; original figure files are untouched.
  execFileSync('/usr/bin/sips',['-Z','3200',input,'--out',asset],{stdio:'pipe'});
  const bytes=await fs.readFile(asset);const iw=bytes.readUInt32BE(16),ih=bytes.readUInt32BE(20);
  const scale=Math.min(1216/iw,620/ih),w=iw*scale,h=ih*scale;
  const slide=p.slides.add();slide.background.fill='#FFFFFF';
  addText(slide,entry.title,{left:32,top:16,width:850,height:45},34,'#26343D',true);
  addText(slide,entry.status,{left:892,top:24,width:356,height:30},19,entry.status.includes('Legacy')||entry.status.includes('legacy')?'#8B5E3C':'#54616C',false,'right');
  slide.images.add({blob:bytes,contentType:'image/png',alt:entry.title,fit:'contain',position:{left:(1280-w)/2,top:76+(620-h)/2,width:w,height:h}});
  slide.speakerNotes.text=[entry.title,entry.status,captions[entry.title]??'',`Source: ${path.relative(root,entry.source)}`,`Source SHA-256: ${entry.sha256}`].filter(Boolean).join('\n\n');
  entry.slide=index+1;entry.embedded_sha256=hash(bytes);entry.frame={left:(1280-w)/2,top:76+(620-h)/2,width:w,height:h};
  const png=await p.export({slide,format:'png',scale:1});
  await fs.writeFile(path.join(build,`slide-${String(index+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
  console.log(`Rendered ${index+1}/${entries.length}: ${entry.title}`);
 }
 const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
 const finalPath=path.join(build,'validated/Figures.pptx');await fs.mkdir(path.dirname(finalPath));
 await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,
  pythonExecutable:path.join(runtime,'python/bin/python3'),
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  explicitTotalSlideCount:entries.length,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
  fontPolicy:{basis:'design',families:['Arial']},
  verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
 const finalDeck=await PresentationFile.importPptx(await FileBlob.load(finalPath));
 for(const [index,slide] of finalDeck.slides.items.entries()) {
  const png=await finalDeck.export({slide,format:'png',scale:1});
  await fs.writeFile(path.join(build,`slide-${String(index+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 }
 for(const [source,sha] of sourceHashes)if(hash(await fs.readFile(source))!==sha)throw new Error('Figure source changed: '+source);
 if(hash(await fs.readFile(path.join(root,'Figure/catalog.json')))!==catalogHash)throw new Error('Figure catalogue changed during assembly');
 await fs.writeFile(path.join(build,'slides.json'),JSON.stringify(entries,null,2));
 await fs.rename(finalPath,destination);
 console.log(JSON.stringify({pptx:destination,slides:entries.length,...(process.argv.includes('--keep-previews')?{buildDirectory:build}:{})}));
 } finally {
  if(!process.argv.includes('--keep-previews'))await fs.rm(build,{recursive:true,force:true});
 }
}

const unknown=process.argv.slice(2).filter(arg=>!['--review','--keep-previews'].includes(arg));
if(unknown.length)throw new Error('The presentation updates the sole PPTX in result (default: Figures.pptx)');
await buildReviewDeck();
