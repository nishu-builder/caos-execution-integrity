const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('../../trajectories/node_modules/playwright');
const base = process.env.BROWSER_URL || 'http://127.0.0.1:18184/trajectories/';
const manifest = require('./runs.json');
const results = require('./results.json');
const load = slug => JSON.parse(fs.readFileSync(path.join(__dirname, '../../docs/trajectories/data/', manifest.cases[slug].id + '.json')));
const url = (slug, fields) => base + '?' + new URLSearchParams({example:manifest.cases[slug].id,...fields});
(async()=>{
 const browser = await chromium.launch();
 try {
  const page = await browser.newPage({viewport:{width:1500,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/data/*.json',r=>r.abort());
  await page.goto(new URL('../experiments.html',base).href);
  await page.getByRole('link',{name:'Researcher: inspect the altered handler'}).click();
  await page.waitForSelector('.file-content pre');
  assert.match(await page.locator('#facts').innerText(),/4 conversations/);
  assert.equal(await page.locator('#conversations button').count(),4);
  assert.match(await page.locator('.file-content').innerText(),/dispatch\.sh/);
  const spoof = load('spoof');
  const replication = results.spoof.grader_observations.find(o=>o.conversation!==spoof.root);
  await page.goto(url('spoof',{conversation:replication.conversation,event:replication.event,tab:'activity'}));
  await page.waitForSelector('#browser:not([hidden])');
  assert.match(await page.locator('#detail').innerText(),/SCORE=1/);
  await page.goto(url('spoof',{conversation:spoof.root,event:manifest.cases.spoof.head,tab:'files',file:'code/dirty/secret.txt'}));
  await page.waitForSelector('.file-content pre');
  assert.match(await page.locator('.file-content pre').innerText(),/DEMO_ONLY_SECRET_4821/);
  const reviewer = spoof.conversations.find(c=>c.title.toLowerCase().includes('reviewer'));
  await page.goto(url('spoof',{conversation:reviewer.id,event:reviewer.head,tab:'files',file:'code/dirty/REVIEW.md'}));
  await page.waitForSelector('.file-content pre');
  assert.match(await page.locator('.file-content pre').innerText(),/secret\.txt/);
  if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'metr-reviewer.png'),fullPage:true});
  const cache=load('cache');
  await page.goto(url('cache',{conversation:cache.root,event:manifest.cases.cache.head,tab:'files',file:'code/dirty/canonical-check.txt'}));
  await page.waitForSelector('.file-content pre');
  assert.match(await page.locator('.file-content pre').innerText(),/REJECTED/);
  const erasure=load('erasure');
  for(const stage of ['setup','attack']){
   await page.goto(url('erasure',{conversation:erasure.root,event:manifest.cases.erasure.stages[stage],tab:'files',file:'code/dirty/logs/trajectory.jsonl'}));
   await page.waitForSelector('.file-content pre');
   const text=await page.locator('.file-content pre').innerText();
   assert.equal(text.includes('"derive"'),stage==='setup');
  }
  await page.goto(new URL('../experiments.html',base).href);
  await page.locator('details summary').click();
  // The report pins the public remote; exercise that link against this test server.
  const failed = new URL(await page.getByRole('link',{name:'Inspect the failed run'}).getAttribute('href'), page.url());
  failed.searchParams.set('remote',new URL('git',base).href);
  await page.goto(failed.href);
  await page.waitForSelector('#browser:not([hidden])');
  assert.match(await page.locator('#facts').innerText(),/4 conversations/);
  await page.setViewportSize({width:390,height:844});
  await page.goto(new URL('../experiments.html',base).href);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  console.log('Passed: METR researcher, replicator and reviewer traces, retained secret, canonical-target failure, log before/after, initial failed run, report links and mobile layout; JSON exports blocked.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
