// Start tests/ui_preview_server.py first. Uses synthetic data only.
// Set QA_PLAYWRIGHT_PATH if Playwright is supplied outside node_modules.
const {chromium} = require(process.env.QA_PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:process.env.QA_BROWSER_CHANNEL || 'msedge',headless:true});
  const out=path.resolve(__dirname,'../artifacts/code_audit/ui');
  fs.mkdirSync(out,{recursive:true});
  const errors=[], payloads=[];
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')payloads.push(r.postDataJSON());});
    await page.goto('http://127.0.0.1:8765');
    await page.getByText('Layanan terhubung',{exact:true}).waitFor();
    // Includes a typical laptop at 125% scaling (CSS viewport 1093 x 614).
    for (const [width,height] of [[1440,900],[1366,768],[1093,614],[1152,528],[390,844]]) {
      await page.setViewportSize({width,height});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),'Landing vertical overflow at '+width+'x'+height);
    }
    await page.setViewportSize({width:1440,height:900});
    await page.screenshot({path:path.join(out,'desktop-landing.png'),fullPage:true});
    await page.getByRole('button',{name:'Cara pakai',exact:true}).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog').evaluate(d=>d.open),false);
    assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Cara pakai');
    await page.locator('#q').fill('cek');
    await page.locator('#q').press('Enter');
    await page.locator('.notice-warning').waitFor();
    assert.equal(payloads.length,0);
    await page.locator('.notice-close').click();
    assert.equal(await page.locator('.notice').count(),0);
    await page.getByRole('button',{name:'Pembangunan manusia'}).click();
    assert.equal(await page.locator('#q').inputValue(),'Apa saja dimensi dalam Indeks Pembangunan Manusia?');
    await page.locator('#q').press('Shift+Enter');
    assert.ok((await page.locator('#q').inputValue()).includes('\n'));
    await page.locator('#q').fill('Apa saja dimensi dalam Indeks Pembangunan Manusia?');
    await page.locator('#model').selectOption('gemma2-base');
    await page.getByRole('button',{name:'Ringkas',exact:true}).click();
    await page.locator('#q').press('Enter');
    await page.locator('#sources article').first().waitFor();
    assert.ok(await page.getByRole('button',{name:'Ringkas',exact:true}).isDisabled());
    assert.equal(await page.locator('#questionForm').isVisible(),false);
    assert.equal(await page.locator('.hero').isVisible(),false);
    assert.ok(await page.locator('#summaryCancelBtn').isVisible());
    assert.ok((await page.locator('#questionSummary').boundingBox()).height<=64);
    await page.screenshot({path:path.join(out,'compact-search.png'),fullPage:true});
    await page.getByText('Baca teks sumber selengkapnya',{exact:true}).first().click();
    // User choice to keep process open must survive completion.
    await page.locator('#thinkToggle').click(); await page.locator('#thinkToggle').click();
    await page.waitForFunction(()=>document.querySelector('#thinkSummary').textContent.startsWith('Penelusuran selesai'));
    assert.equal(await page.locator('#thinkToggle').getAttribute('aria-expanded'),'true');
    assert.equal(await page.locator('#source-1 details').evaluate(d=>d.open),true);
    assert.equal(await page.locator('#sourceCount').textContent(),'2');
    assert.deepEqual(payloads[0],{question:'Apa saja dimensi dalam Indeks Pembangunan Manusia?',model_key:'gemma2-base',use_rag:true,response_style:'ringkas'});
    await page.getByText('Lihat rincian kandidat sumber',{exact:true}).click();
    await page.screenshot({path:path.join(out,'desktop-results.png'),fullPage:true});
    await page.locator('#answer .citation-ref').last().click();
    assert.equal(new URL(page.url()).hash,'#source-2');
    const previous=await page.locator('#answer').textContent();
    assert.equal(await page.locator('#questionForm').isVisible(),false);
    await page.locator('#editQuestionBtn').click();
    assert.equal(await page.evaluate(()=>document.activeElement.id),'q');
    await page.locator('#q').fill('server sibuk');await page.locator('#btn').click();
    await page.locator('.notice-error').waitFor();
    assert.equal(await page.locator('#answer').textContent(),previous);
    await page.screenshot({path:path.join(out,'desktop-error.png'),fullPage:true});
    await page.locator('.notice-error').waitFor({state:'detached',timeout:10000});
    assert.match(await page.locator('#error').textContent(),/Server sedang sibuk/);
    await page.locator('#q').fill('tunggu jawaban');await page.locator('#btn').click();
    await page.waitForFunction(()=>document.querySelector('#thinkSummary').textContent.includes('Menunggu'));
    await page.locator('#summaryCancelBtn').click();
    await page.waitForFunction(()=>!document.querySelector('#btn').disabled);
    assert.match(await page.locator('#error').textContent(),/dibatalkan/);
    assert.equal(await page.locator('#ansCard').isVisible(),false);
    await page.locator('#q').fill('jawaban gagal');await page.locator('#btn').click();
    await page.waitForFunction(()=>document.querySelector('#thinkSummary').textContent==='Pemrosesan belum selesai');
    assert.match(await page.locator('#error').textContent(),/belum dapat dihubungi/);
    assert.equal(await page.locator('#btn').isDisabled(),false);
    await page.locator('#q').fill('Apa saja dimensi IPM?');await page.locator('#btn').click();
    await page.waitForFunction(()=>document.querySelector('#thinkSummary').textContent.startsWith('Penelusuran selesai'));
    assert.equal(await page.locator('#thinkToggle').getAttribute('aria-expanded'),'false');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'answerTitle');
    assert.equal(await page.locator('#questionForm').isVisible(),false);
    const related=page.locator('a.other-src-item').first();
    assert.equal(await related.getAttribute('target'),'_blank');
    const originalBorder=await related.evaluate(n=>getComputedStyle(n).borderColor);
    await related.hover();
    await page.waitForFunction(original=>getComputedStyle(document.querySelector('a.other-src-item')).borderColor!==original,originalBorder);
    await page.screenshot({path:path.join(out,'related-hover.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'mobile-results.png'),fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Mobile results overflow');
    await page.reload();
    await page.getByText('Layanan terhubung',{exact:true}).waitFor();
    await page.screenshot({path:path.join(out,'mobile-landing.png'),fullPage:true});
    for(const width of [320,360,650,768,1024]){
      await page.setViewportSize({width,height:900});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Landing overflow at '+width);
    }
    await page.getByRole('button',{name:'Cara kerja',exact:true}).click();
    await page.getByRole('dialog').waitFor();
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    await page.locator('#modalClose').click();
    const offline=await browser.newPage();
    offline.on('pageerror',e=>errors.push(e.message));
    await offline.route('**/api/health',route=>route.abort());
    await offline.goto('http://127.0.0.1:8765');
    await offline.getByText('Layanan tidak terjangkau',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log('Browser checks passed: desktop/mobile layouts, guides, keyboard, validation, model/style payload, streaming, source links, process state, timed error bubble, HTTP failure, cancellation, retry and offline service.');
    console.log('Screenshots: '+out);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
