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
const app=path.resolve(process.env.PLASTPRIOR_DASHBOARD_ROOT || path.join(root,'audit_archive/dashboard_runtime_20261026'));
const lock=JSON.parse(await fs.readFile(path.join(root,'FigureCode/figure_sources.json'),'utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const context=await browser.newContext({viewport:{width:1672,height:1100},deviceScaleFactor:2});
 const page=await context.newPage();
 page.on('pageerror', e=>console.error(e.message));
 await page.goto(url);
 // Bind the screenshot to the exact local production bundle being served.
 const bundleHashes={};
 const scripts=(await page.locator('script[src]').evaluateAll(nodes=>nodes.map(node=>node.src)))
   .filter(src=>new URL(src).origin===new URL(url).origin);
 if (!scripts.length) throw new Error('No application bundle found');
 for (const src of scripts) {
   const relative=new URL(src).pathname.replace(/^\//,'');
   const served=await (await page.request.get(src)).body();
   const local=await fs.readFile(path.join(app,'app/dist',relative));
   const digest=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
   if(digest(served)!==digest(local))throw new Error('Dashboard server does not match the selected local build');
   bundleHashes[relative]=digest(local);
 }
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
 await fs.writeFile(path.join(output,'visible_text.txt'),visible);
 const hashes={};
 for(const file of ['app/src/features/overview/ChemicalSvgViz.jsx','app/src/core/plastprior.js','app/src/core/priorityScore.js','app/src/core/exposureScore.js','app/src/core/hazardComputationStatus.js','app/src/core/fishAcuteEvidence.js','app/src/core/auditDatabase.js','app/src/ChemicalHazardVisualizer.jsx']) hashes[file]=crypto.createHash('sha256').update(await fs.readFile(path.join(app,file))).digest('hex');
 await fs.writeFile(path.join(output,'caption_facts.json'),JSON.stringify({run_id:lock.run_id,compound:'WHHGLZMJPXIBIX-UHFFFAOYSA-N',name:'Decabromodiphenyl oxide',viewport_css:[1672,1100],device_scale:2,crop:'Dashboard content and results list; upload header excluded.',pixel_edits:'None',dashboard_revision:'verified local Dashboard implementation; exact implementation recorded by source SHA-256',dashboard_bundle_sha256:bundleHashes,dashboard_source_sha256:hashes},null,2));
} finally {await browser.close();}
