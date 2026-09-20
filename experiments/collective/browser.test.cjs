const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('../../trajectories/node_modules/playwright');
const base = process.env.BROWSER_URL || 'http://127.0.0.1:18184/trajectories/';
(async()=>{
 const browser=await chromium.launch();
 try {
  const page=await browser.newPage({viewport:{width:1500,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/data/*.json',r=>r.abort());
  const report=new URL('../experiments.html',base).href;
  await page.goto(report);
  const links={};
  for(const id of ['full-run','researcher','procedure','during','replication','after','review'])
   links[id]=new URL(await page.locator('#'+id).getAttribute('href'),report).href;
  await page.goto(links.researcher);
  await page.waitForSelector('#browser:not([hidden])');
  assert.match(await page.locator('#detail').innerText(),/SCORE=1/);
  assert.match(await page.locator('#facts').innerText(),/5 conversations/);
  assert.equal(await page.locator('#conversations button').count(),5);
  for(const stage of ['during','after']){
   await page.goto(links[stage]);await page.waitForSelector('.file-content pre');
   const text=await page.locator('.file-content pre').innerText();
   assert.equal(text.includes('BASH_ENV'),stage==='during');
  }
  await page.goto(links.procedure);await page.waitForSelector('.file-content pre');
  assert.match(await page.locator('.file-content pre').innerText(),/BASH_ENV/);
  await page.goto(links.replication);await page.waitForSelector('#browser:not([hidden])');
  assert.match(await page.locator('#detail').innerText(),/SCORE=1/);
  assert.match(await page.locator('#detail').innerText(),/harbor-29/);
  if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'collective-replication.png'),fullPage:true});
  await page.goto(links.review);await page.waitForSelector('.file-content pre');
  assert.match(await page.locator('.file-content pre').innerText(),/BASH_ENV/);
  await page.goto(report);
  assert.equal(await page.locator('tbody tr').count(),2);
  if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'collective-report.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  console.log('Passed: five-agent report links, working research and replication, captured/restored environment, shared procedure, review and mobile layout; JSON exports blocked.');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
