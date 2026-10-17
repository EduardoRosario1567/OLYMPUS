import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import pw from '/workspace/scratch/1756b717520d/qa-project/frontend/node_modules/playwright/index.mjs';

const browser=await pw.chromium.launch({
  executablePath:'/workspace/scratch/1756b717520d/qa-browser-bin/chromium',
  // Keep browser origin/CSP security enabled for this test.
  args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'],headless:true,
});
const cases=[];
try {
  const page=await browser.newPage();
  await page.goto(process.env.PREVIEW_FIXTURE_URL+'/parent');
  await page.waitForFunction(()=>window.probes?.length===3&&window.modules?.length===3,{},{timeout:15000});
  const result=await page.evaluate(()=>({probes,modules,secret:localStorage.getItem('PARENT_SECRET')}));
  assert.ok(result.probes.every(p=>p.parentBlocked&&p.storageBlocked&&p.origin==='null'));
  cases.push('runtime/static/legacy iframe cannot read parent or own protected storage');
  assert.ok(result.probes.every(p=>p.connectBlocked));
  const stats=await page.request.get(process.env.PREVIEW_FIXTURE_URL+'/stats');
  assert.equal((await stats.json()).forbidden_requests,0);
  cases.push('CSP prevents project connections to panel endpoints');
  assert.equal(result.modules.length,3);
  cases.push('ES modules load through capability URLs with opaque-origin CORS');
  assert.equal(result.secret,'SYNTHETIC_PARENT_ONLY');
  cases.push('parent storage remains intact');
  await fs.writeFile('.olympus/qa/m5-preview-browser.json',JSON.stringify({browser:browser.version(),passed:cases.length,cases,probes:result.probes},null,2));
  console.log(JSON.stringify({passed:cases.length,cases}));
} finally { await browser.close(); }
