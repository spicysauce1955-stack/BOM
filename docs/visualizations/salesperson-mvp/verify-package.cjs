const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL,fileURLToPath}=require('node:url');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const root=__dirname,files=[];
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){assert.ok(!e.isSymbolicLink(),'Package must not contain symlinks');const f=path.join(dir,e.name);if(e.isDirectory())walk(f);else files.push(f);}}
function localTarget(url){
  if(url.protocol!=='file:')return;
  const file=fileURLToPath(url);
  assert.ok(file.startsWith(root+path.sep),'Reference escapes package: '+file);
  assert.ok(fs.existsSync(file),'Missing local reference: '+file);
}
(async()=>{
  walk(root);
  for(const file of files.filter(f=>f.endsWith('.md'))){
    for(const [,href] of fs.readFileSync(file,'utf8').matchAll(/\]\(([^\s)]+)\)/g))localTarget(new URL(href,pathToFileURL(file)));
  }
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'references/source-manifest.json'),'utf8'));
  for(const entry of manifest.files)assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,entry.snapshot))).digest('hex'),entry.sha256);
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||undefined,args:['--no-sandbox','--disable-dev-shm-usage']});
  try{
    const context=await browser.newContext({offline:true,viewport:{width:1440,height:1100}});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('requestfailed',r=>errors.push(r.url()+': '+r.failure()?.errorText));
    async function checkPage(){
      const refs=await page.locator('a[href],link[href],script[src],img[src]').evaluateAll(els=>els.map(el=>el.href||el.src));
      refs.forEach(href=>localTarget(new URL(href)));
      await page.locator('img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
    }
    const pages=files.filter(f=>f.endsWith('.html'));
    for(const file of pages){
      await page.goto(pathToFileURL(file).href);await checkPage();
      for(const attr of ['data-step','data-session']){
        const values=await page.locator('['+attr+']').evaluateAll(els=>els.map(el=>el.getAttribute(el.hasAttribute('data-step')?'data-step':'data-session')));
        for(const value of values){await page.locator('['+attr+'="'+value+'"]').click();await checkPage();}
      }
    }
    await page.goto(pathToFileURL(path.join(root,'index.html')).href);
    await page.locator('[data-step="2"]').click();await page.locator('[data-select="side"]').click();await page.locator('[data-detail-tab="Base"]').click();
    await page.screenshot({path:process.env.PACKAGE_SCREENSHOT||'/tmp/bom-packaged-index.png',fullPage:true});
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({files:files.length,htmlPages:pages.length,sourceSnapshots:manifest.files.length,offline:true,localLinks:'pass',sourceHashes:'pass',errors}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
