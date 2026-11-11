/* End-to-end behavior against either the static site or the local API server.
   NODE_PATH must resolve Playwright; run: node test_ui.cjs http://127.0.0.1:8768 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const url = process.argv[2] || 'http://127.0.0.1:8768';
const out = path.join(__dirname, '..', 'jinkui-work', 'preview');

(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined});
  const context = await browser.newContext({viewport:{width:1360,height:1000}});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.addInitScript(() => {
    localStorage.setItem('tcm-answered', JSON.stringify([1,2185]));
    localStorage.setItem('tcm-subject', JSON.stringify('金匮要略'));
  });
  await page.goto(url);
  await page.waitForFunction(() => state.all.length > 7000 && current());
  assert.equal(await page.locator('#subject').inputValue(), '金匮要略');
  const counts = await page.evaluate(() => ({all:state.all.length, subject:state.questions.length, mode:state.staticMode}));
  assert(counts.subject > 500);
  await page.evaluate(() => { state.index=600;resetAnswer();render(); });
  assert.match(await page.locator('#position').textContent(), /601/);
  await page.locator('#next').click();
  assert.equal(await page.evaluate(() => state.index),601);

  await page.selectOption('#questionType','A1');
  await page.selectOption('#answerStatus','source_answer_present');
  const keyFor = async () => {
    const id = await page.evaluate(() => current().id);
    if (counts.mode) return page.evaluate(() => current().answer_key);
    return (await (await fetch(url + '/api/questions/' + id + '/answer')).json()).answer_key;
  };
  let key = await keyFor();
  assert(key);
  await page.locator('.choice').filter({has:page.locator('.choice-letter', {hasText:new RegExp('^'+key+'$')})}).click();
  assert.equal(await page.locator('.answer').count(),0);
  await page.locator('#toggleAnswer').click();
  await page.waitForSelector('.answer');
  assert.equal(await page.locator('.answer-title').textContent(),'回答正确');

  await page.selectOption('#questionType','Multiple');
  key = await keyFor();
  assert(key && key.length > 1);
  for (const letter of key) {
    const index = await page.evaluate(letter => current().options.findIndex(o => o.letter === letter),letter);
    await page.locator('[data-option="'+index+'"]').click();
  }
  await page.locator('#toggleAnswer').click();
  await page.waitForSelector('.answer');
  assert.equal(await page.locator('.answer-title').textContent(),'回答正确');
  await page.locator('#next').click();
  key=await keyFor();
  const wrong = await page.evaluate(key => current().options.findIndex(o => !key.includes(o.letter)),key);
  await page.locator('[data-option="'+(wrong<0?0:wrong)+'"]').click();
  await page.locator('#toggleAnswer').click();
  await page.waitForSelector('.answer');
  assert.equal(await page.locator('.answer-title').textContent(),'回答不正确');

  await page.selectOption('#answerStatus','needs_review');
  await page.locator('#toggleAnswer').click();
  await page.waitForSelector('.answer');
  assert.equal(await page.locator('.answer-title').textContent(),'本题不自动判分');
  assert.equal(await page.locator('.choice.correct,.choice.incorrect').count(),0);

  await page.selectOption('#answerStatus','source_answer_present');
  await page.selectOption('#questionType','FillBlank');
  await page.locator('#draft').fill('我的练习答案');
  const initialIndex=await page.evaluate(() => state.index);
  await page.locator('#draft').press('ArrowRight');
  assert.equal(await page.evaluate(() => state.index),initialIndex);
  await page.locator('#toggleAnswer').click();
  await page.waitForSelector('.answer');
  assert.equal(await page.locator('.answer-title').textContent(),'本题不自动判分');
  assert.equal(await page.locator('#draft').inputValue(),'我的练习答案');

  await page.selectOption('#questionType','A3');
  assert((await page.locator('.group-context').textContent()).length>35);
  await page.screenshot({path:path.join(out,'quiz-desktop.png'),fullPage:true});
  await page.setViewportSize({width:360,height:800});
  await page.locator('.group-context').scrollIntoViewIfNeeded();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:path.join(out,'quiz-mobile.png')});

  await page.setViewportSize({width:1360,height:1000});
  await page.selectOption('#subject','中医内科');
  assert.equal(await page.evaluate(() => state.questions.length),2185);
  assert(await page.locator('#chapterField').isHidden());
  assert(await page.locator('#systemField').isVisible());
  await page.selectOption('#system','肺系');
  assert(await page.evaluate(() => state.questions.every(q => state.meta.systems['肺系'].includes(q.topic))));
  await page.selectOption('#system','');
  await page.selectOption('#questionType','Multiple');
  await page.selectOption('#answerStatus','source_answer_present');
  key=await keyFor();
  assert(key && key.length>1);
  for (const letter of key) {
    const index=await page.evaluate(letter => current().options.findIndex(o=>o.letter===letter),letter);
    await page.locator('[data-option="'+index+'"]').click();
  }
  await page.locator('#toggleAnswer').click();
  await page.waitForSelector('.answer');
  assert.equal(await page.locator('.answer-title').textContent(),'回答正确');
  const stored=await page.evaluate(() => JSON.parse(localStorage.getItem('tcm-answered')));
  assert(stored.includes(1) && stored.includes(2185) && stored.length>2);

  await page.selectOption('#subject','金匮要略');
  await page.selectOption('#chapter','附录·模拟试卷二');
  assert(await page.evaluate(() => state.questions.length>50 && state.questions.every(q=>q.chapters.includes('附录·模拟试卷二'))));
  const duplicate=await page.evaluate(() => state.all.find(q=>q.subject==='金匮要略' && q.sources.length>1));
  await page.selectOption('#chapter','');
  await page.selectOption('#source',String(duplicate.sources[1].source_id));
  assert(await page.evaluate(id => state.questions.some(q=>q.id===id),duplicate.id));
  assert(await page.evaluate(() => state.questions.every(q=>q.source_ids.includes(Number(document.getElementById('source').value)))));
  assert.equal(await page.locator('.source').getByText('第 1 页',{exact:false}).count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',url,...counts,checks:18,consoleErrors:errors.length}));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
