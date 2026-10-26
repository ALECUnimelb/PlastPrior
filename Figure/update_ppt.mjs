// Update the existing review deck from verified current figures; no plotting here.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
const require=createRequire(import.meta.url);
const {FileBlob,PresentationFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const figuresDir=path.dirname(fileURLToPath(import.meta.url));
const workspaceDir=path.dirname(figuresDir);
const runtime=path.join(process.env.HOME,'.cache/codex-runtimes/codex-primary-runtime/dependencies');
process.env.RUNTIME_NODE_MODULES ??= path.join(runtime,'node/node_modules');
const skill=process.env.PRESENTATIONS_SKILL_DIR ?? path.join(process.env.HOME,'.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11618/skills/presentations');
const pythonExecutable=process.env.PRESENTATIONS_PYTHON ?? path.join(runtime,'python/bin/python3');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
execFileSync(path.join(workspaceDir,'.venv/bin/python'),[path.join(figuresDir,'verify_figures.py')],{cwd:workspaceDir,stdio:'inherit'});
const names=['Fig1','Fig2','Fig3','Fig4','Fig5','ExtendedDataFig1','ExtendedDataFig2','ExtendedDataFig3','ExtendedDataFig4'];
const lock=JSON.parse(await fs.readFile(path.join(figuresDir,'figure_sources.json'),'utf8'));
const buildRoot=path.join(workspaceDir,'audit_archive/ppt_builds');
await fs.mkdir(buildRoot,{recursive:true});
const build=await fs.mkdtemp(path.join(buildRoot,'ppt-'));
const decks=await Promise.all((await fs.readdir(figuresDir)).filter(name=>/^Final_Figures.*\.pptx$/.test(name)).map(async name=>({path:path.join(figuresDir,name),mtime:(await fs.stat(path.join(figuresDir,name))).mtimeMs})));
decks.sort((a,b)=>b.mtime-a.mtime);
const template=process.argv[2]?path.resolve(process.argv[2]):decks[0]?.path;
if(!template)throw new Error('Provide an existing review deck as the first argument.');
const stamp=new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+Z$/,'Z');
const destination=process.argv[3]?path.resolve(process.argv[3]):path.join(figuresDir,`Final_Figures_${stamp}.pptx`);
try {await fs.access(destination);throw new Error('Output already exists: '+destination);} catch(error) {if(error.code!=='ENOENT')throw error;}
const source=path.join(build,'before.pptx');
await fs.copyFile(template,source);
const sourceHash=crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex');
const p=await PresentationFile.importPptx(await FileBlob.load(source));
await fs.writeFile(path.join(build,'before-inspection.json'),JSON.stringify(await p.inspect({kind:'slide,textbox,image,notes',maxChars:30000}),null,2));
const captions={};
for(const section of (await fs.readFile(path.join(figuresDir,'captions_draft.md'),'utf8')).split('\n## ').slice(1)) {
 const [heading,...body]=section.split('\n');captions[heading.split(' | ')[0]]=heading+'\n\n'+body.join('\n').trim().replaceAll('**','');
}
if(p.slides.items.length!==9)throw new Error('Expected nine slides');
for(const [i,slide] of p.slides.items.entries()) {
 const before=await p.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(build,`before-${i+1}.png`),new Uint8Array(await before.arrayBuffer()));
 if(slide.images.items.length!==1)throw new Error(`Expected one figure on slide ${i+1}`);
 const name=names[i], title=name.startsWith('Extended')?`Extended Data Fig. ${name.slice(-1)}`:`Fig. ${name.slice(-1)}`;
 const imagePath=path.join(figuresDir,name,'output',name+'.png');const bytes=await fs.readFile(imagePath);
 const iw=bytes.readUInt32BE(16),ih=bytes.readUInt32BE(20),scale=Math.min(1216/iw,632/ih),w=iw*scale,h=ih*scale;
 const img=slide.images.items[0];img.replace({blob:bytes,contentType:'image/png',fit:'contain',alt:title});
 img.frame={left:(1280-w)/2,top:72+(632-h)/2,width:w,height:h};img.crop={left:0,top:0,right:0,bottom:0};img.lockAspectRatio=true;
 if(!captions[title])throw new Error('Missing caption '+title);
 slide.speakerNotes.text=captions[title]+`\n\nSource: ${imagePath}\nPlastPrior run: ${lock.run_id}\nAnalysis SHA-256: ${lock.files.analysis.sha256}\nFigure PNG SHA-256: ${crypto.createHash('sha256').update(bytes).digest('hex')}`;
 console.log(`Updated slide ${i+1}/9: ${title}`);
}
const candidatePath=path.join(build,'candidate.pptx');await (await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath=path.join(build,'final/Final_Figures.pptx');await fs.mkdir(path.dirname(finalPath),{recursive:true});
await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'reference',families:['Arial'],referencePath:source,referenceSha256:sourceHash},
 verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const [i,slide] of final.slides.items.entries()) {
 const png=await final.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
 console.log(`Rendered final slide ${i+1}/9`);
}
await fs.copyFile(finalPath,destination,1);
console.log(JSON.stringify({pptx:destination,reviewDirectory:build}));
