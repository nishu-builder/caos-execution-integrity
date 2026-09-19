const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const {chromium}=require('playwright');
const base=process.env.BROWSER_URL||'http://127.0.0.1:18184/trajectories/';
const origin=new URL(base).origin;
const repo=fs.mkdtempSync(path.join(os.tmpdir(),'trajectory-git-test-'));
const git=(...args)=>execFileSync('git',['-C',repo,...args],{encoding:'utf8'}).trim();
(async()=>{
 git('init','--quiet');git('config','user.name','Browser test');git('config','user.email','test@example.invalid');
 fs.mkdirSync(path.join(repo,'.caos'));fs.writeFileSync(path.join(repo,'.caos','identity.json'),JSON.stringify({id:'fresh-run'}));
 fs.writeFileSync(path.join(repo,'.caos','title'),'A new run outside the examples');
 fs.writeFileSync(path.join(repo,'hello.txt'),'Freshly fetched through Git.\n');
 git('add','.');git('commit','--quiet','-m','conversation.root');const head=git('rev-parse','HEAD');
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const query=new URLSearchParams({remote:repo,head});
  await page.goto(base+'?'+query);await page.waitForSelector('#browser:not([hidden])').catch(async e=>{throw Error((await page.locator('#notice').innerText())+' '+errors.join('; '));});
  assert.match(await page.locator('#facts').innerText(),/1 conversations/);
  assert.match(await page.locator('#description').innerText(),new RegExp(head));
  await page.click('[data-tab="files"]');assert.match(await page.locator('.file-content').innerText(),/Freshly fetched through Git/);
  const objectURL=await page.locator('#event-heading a').getAttribute('href');
  const result=await page.request.get(origin+objectURL);assert.equal(result.status(),200);
  assert.equal(createHash('sha1').update(await result.body()).digest('hex'),head);
  await page.reload();await page.waitForSelector('.file-content');assert.match(await page.locator('.file-content').innerText(),/Freshly fetched through Git/);
  assert.equal(new URL(page.url()).searchParams.get('remote'),repo);
  // A different commit on the same remote must produce different data, not a fixture/cache hit.
  fs.writeFileSync(path.join(repo,'hello.txt'),'Second independent snapshot.\n');git('add','.');git('commit','--quiet','-m','tool.complete');const second=git('rev-parse','HEAD');
  await page.fill('#source-head',second);await page.click('#load-run button');
  await page.waitForFunction(h=>document.querySelector('#description').textContent.includes(h),second);
  await page.click('[data-tab="files"]');assert.match(await page.locator('.file-content').innerText(),/Second independent snapshot/);
  await page.selectOption('#side','before');assert.match(await page.locator('.file-content').innerText(),/Freshly fetched through Git/);
  await page.selectOption('#example','repair');await page.waitForFunction(()=>document.querySelector('#facts').textContent.includes('3 conversations'));
  assert.equal(new URL(page.url()).searchParams.has('remote'),false);
  let response=await page.request.post(origin+'/api/load',{data:{kind:'remote',source:repo,head:'not-a-hash'}});assert.equal(response.status(),400);
  response=await page.request.post(origin+'/api/load',{headers:{Origin:'https://another-site.invalid'},data:{kind:'remote',source:repo,head}});assert.equal(response.status(),403);
  response=await page.request.post(origin+'/api/load',{headers:{'Content-Type':'text/plain'},data:'{}'});assert.equal(response.status(),415);
  if(process.env.LIVE_CAOS_SERVER){
   await page.fill('#source-url',process.env.LIVE_CAOS_SERVER);await page.selectOption('#source-kind','server');
   await page.fill('#source-head','845c4cd46019a73064cbe3c9d4927a668046d315');await page.click('#load-run button');
   await page.waitForFunction(()=>document.querySelector('#description').textContent.startsWith('Loaded from http'));
   assert.match(await page.locator('#facts').innerText(),/3 conversations/);
   assert.equal(new URL(page.url()).searchParams.get('server'),process.env.LIVE_CAOS_SERVER);
   await page.screenshot({path:process.env.SCREENSHOT_PATH||'/tmp/trajectory-remote.png',fullPage:true});
  }
  // The static hosted page explains how to start the reader; it never pretends to connect.
  await page.route('**/api/viewer',route=>route.fulfill({status:404,body:'Not found'}));
  await page.goto(base+'?'+query);await page.waitForSelector('#local-help:not([hidden])');
  assert.match(await page.locator('#launch-command').innerText(),/serve.py --remote/);
  assert.match(await page.locator('#launch-command').innerText(),new RegExp(head));
  assert.deepEqual(errors,[]);
  console.log('Passed: fresh Git remote, new commit, before/after, raw object integrity, deep-link reload, example switching, local API protections, hosted-page instructions.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>fs.rmSync(repo,{recursive:true,force:true}));
