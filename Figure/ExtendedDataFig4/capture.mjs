// Capture the real application after loading the locked publication pair.
// Requires Playwright (set NODE_PATH to an existing installation if needed).
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const [url,output]=process.argv.slice(2);
const lock=JSON.parse(await fs.readFile(path.join(root,'Figure/figure_sources.json'),'utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const context=await browser.newContext({viewport:{width:1672,height:1100},deviceScaleFactor:2});
 const page=await context.newPage();
 page.on('pageerror', e=>console.error(e.message));
 await page.goto(url);
 await page.waitForFunction(() => {
   const input=document.querySelector('[aria-label="Upload dashboard data file"]');
   return input && !input.disabled;
 }, null, {timeout:120000});
 await page.getByLabel('Upload dashboard data file',{exact:true}).setInputFiles(path.join(root,lock.files.publication.path));
 await page.getByText('Decabromodiphenyl oxide',{exact:true}).waitFor({timeout:120000});
 await page.getByLabel('Upload optional audit database',{exact:true}).setInputFiles(path.join(root,lock.files.dashboard.path));
 // Loaded evidence must contain the selected source's real literature count.
 const panel=page.locator('div.flex.flex-col.gap-6.lg\\:flex-row.lg\\:items-stretch');
 await panel.getByText('655',{exact:true}).waitFor({timeout:120000});
 await panel.getByText('NCBI PubMed Title/Abstract',{exact:true}).first().waitFor({state:'attached'});
 await panel.getByText('ID: WHHGLZMJPXIBIX-UHFFFAOYSA-N',{exact:true}).waitFor();
 await panel.getByText('GC-EI-MS',{exact:true}).waitFor({timeout:120000});
 await panel.getByText('Carcinogenicity_CAESAR',{exact:true}).waitFor();
 await page.evaluate(()=>document.fonts.ready);
 const visible=await panel.textContent();
 if(/Evidence not loaded|Details not loaded|Load the paired detail database/.test(visible)) throw new Error('Audit evidence is not loaded');
 if(!visible.includes('26') || !visible.includes('16') || visible.includes('2,6-Toluenediamine (Demo)')) throw new Error('Unexpected dashboard record');
 await panel.screenshot({path:path.join(output,'ExtendedDataFig4.png'),scale:'device',animations:'disabled'});
 await fs.mkdir(path.join(output,'source_data'),{recursive:true});
 await fs.writeFile(path.join(output,'source_data/visible_text.txt'),visible);
 const app=path.resolve(root,'../ChemicalPrioDashboard');
 const hashes={};
 for(const file of ['app/src/features/overview/ChemicalSvgViz.jsx','app/src/core/plastprior.js','app/src/core/priorityScore.js','app/src/core/exposureScore.js','app/src/core/hazardComputationStatus.js','app/src/core/fishAcuteEvidence.js','app/src/core/auditDatabase.js','app/src/ChemicalHazardVisualizer.jsx']) hashes[file]=crypto.createHash('sha256').update(await fs.readFile(path.join(app,file))).digest('hex');
 await fs.writeFile(path.join(output,'caption_facts.json'),JSON.stringify({run_id:lock.run_id,compound:'WHHGLZMJPXIBIX-UHFFFAOYSA-N',name:'Decabromodiphenyl oxide',viewport_css:[1672,1100],device_scale:2,crop:'Dashboard content and results list; upload header excluded.',pixel_edits:'None',dashboard_revision:'isolated working snapshot; exact implementation recorded by source SHA-256',dashboard_source_sha256:hashes},null,2));
} finally {await browser.close();}
