import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require('../frontend/node_modules/playwright');
const file = resolve(process.argv[2] || '/tmp/olympus-rosales-mvp/index.html');
if (!readFileSync(file,'utf8').includes('Rosales Café')) throw new Error('Unexpected project');
const browser = await chromium.launch({ headless:true });
try {
  for (const viewport of [{width:390,height:844}, {width:1440,height:900}]) {
    const context = await browser.newContext({ viewport,locale:'pt-BR' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(pathToFileURL(file).toString(), {waitUntil:'load'});
    await page.getByRole('heading', {name:/Café para quem/i}).waitFor();
    await page.getByRole('navigation', {name:'Navegação principal'}).getByRole('link',{name:'Conceito'}).click();
    if (!(await page.evaluate(() => location.hash))?.includes('conceito')) throw new Error('Anchor navigation failed');
    await page.getByRole('link',{name:/Conheça o conceito/}).click();
    const overflow=await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth+1);
    if (overflow) throw new Error('Horizontal overflow '+viewport.width);
    if (errors.length) throw new Error('JS errors: '+errors.join(';'));
    const css=await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor);
    if (!css || css==='rgba(0, 0, 0, 0)') throw new Error('CSS failed to load');
    console.log('ROSALES_BROWSER_PASSED viewport='+viewport.width+' title='+await page.title());
    await context.close();
  }
} finally { await browser.close(); }
